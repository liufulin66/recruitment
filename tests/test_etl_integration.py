"""独立测试库中验证批内幂等、其他快照隔离与失败回滚。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from etl.repository import replace_snapshot
from etl.repository import remove_snapshot
from etl.run_etl import run_snapshot
from etl.sources import ETLValidationError
from etl.transforms import clean_jobs
from tests.support import MySQLTestCase


class TestSnapshotReplacement(MySQLTestCase):
    def rows(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT snapshot_id, job_name, city, salary_avg FROM jobs ORDER BY snapshot_id, job_name")
            return cur.fetchall()

    def test_csv_repeat_import_does_not_change_other_snapshot(self):
        before = [r for r in self.rows() if r[0] == 1]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "jobs.csv"
            pd.DataFrame({
                "title": ["后端", "后端"], "company": ["A", "A"], "city": ["杭州", "杭州"],
                "salary": ["10-20K", "10-20K"], "experience": ["1-3年", "1-3年"],
                "education": ["本科", "本科"],
            }).to_csv(source, index=False)
            config = {"label": "2020", "source": "fixture", "period": "2020", "note": "",
                      "form": "csv", "path": str(source), "has_skills": False,
                      "columns": {c: c for c in ("title", "company", "city", "salary", "experience", "education")}}
            stats = run_snapshot(self.conn, config)
            first = self.rows()
            run_snapshot(self.conn, config)
            self.assertEqual(self.rows(), first)
        self.assertEqual(stats["jobs"], 1)
        self.assertEqual(stats["去重移除"], 1)
        self.assertEqual([r for r in first if r[0] == 1], before)

    def test_invalid_source_preserves_existing_data(self):
        before = self.rows()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.csv"
            pd.DataFrame({"title": ["后端"]}).to_csv(source, index=False)
            config = {"label": "2020", "form": "csv", "path": str(source), "columns": {}, "has_skills": False}
            with self.assertRaises(ETLValidationError):
                run_snapshot(self.conn, config)
        self.assertEqual(self.rows(), before)

    def test_write_failure_rolls_back_jobs_and_metadata(self):
        before = self.rows()
        df, _ = clean_jobs(pd.DataFrame({
            "title": ["替换岗位"], "company": ["A"], "city": ["杭州"], "salary": ["10K"],
            "experience": ["1-3年"], "education": ["本科"], "key_word": [None],
        }))
        meta = {"label": "2018", "source": "should-roll-back", "period": "2018", "note": ""}
        with patch("etl.repository.insert_skills", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                replace_snapshot(self.conn, meta, df, [])
        self.assertEqual(self.rows(), before)
        with self.conn.cursor() as cur:
            cur.execute("SELECT source FROM snapshots WHERE label = '2018'")
            self.assertEqual(cur.fetchone()[0], "fixture-2018")

    def test_fresh_install_import_order_defaults_to_2020(self):
        from queries import resolve_snapshot

        with self.conn.cursor() as cur:
            for table in ("job_skills", "jobs", "snapshots"):
                cur.execute(f"DELETE FROM {table}")
        self.conn.commit()
        jobs, _ = clean_jobs(pd.DataFrame({
            "title": ["旧期岗位"], "company": ["A"], "city": ["杭州"], "salary": ["10K"],
            "experience": ["1-3年"], "education": ["本科"], "key_word": [None],
        }))
        meta18 = {"label": "2018", "source": "fixture-2018", "period": "2018", "note": ""}
        meta20 = {"label": "2020", "source": "fixture-2020", "period": "2020", "note": ""}
        replace_snapshot(self.conn, meta18, jobs, [])
        sid20 = replace_snapshot(self.conn, meta20, jobs, [], replaces="2021")
        self.assertEqual(resolve_snapshot(self.conn, {}), sid20)
        replace_snapshot(self.conn, meta18, jobs, [])
        self.assertEqual(resolve_snapshot(self.conn, {}), sid20)


class TestRetiredSnapshot(MySQLTestCase):
    """专门构造历史 2021；id 故意与年份不同，覆盖整个事务的内容。"""

    def setUp(self):
        super().setUp()
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE snapshot_id=2")
            cur.execute("DELETE FROM snapshots WHERE id=2")
            cur.execute("INSERT INTO snapshots (id,label,source,period,note) "
                        "VALUES (77,'2021','legacy','2021','old')")
            cur.execute("INSERT INTO jobs (snapshot_id,job_name,city,salary_avg) "
                        "VALUES (77,'旧岗位','上海',12345)")
            cur.execute("INSERT INTO job_skills (snapshot_id,source_map_id,key_word,skill) "
                        "VALUES (77,42,'old','legacy-skill')")
            cur.execute("INSERT INTO captcha_challenges (id,code,expires_at) "
                        "VALUES ('keep-captcha','TEST','2099-01-01')")
        self.conn.commit()
        self.config = {"label": "2020", "source": "new-source", "period": "2020 年 4 月公开快照",
                       "note": "12 城市 IT 岗位样本，无逐条发布日期，无技能数据",
                       "form": "csv", "has_skills": False, "replaces": "2021",
                       "columns": {c: c for c in ("title", "company", "city", "salary", "experience", "education")}}
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "jobs.csv"
        self.config["path"] = str(self.path)
        self.source = pd.DataFrame({
            "title": ["新岗位"], "company": ["A"], "city": ["杭州"], "salary": ["8000元-13000元"],
            "experience": [None], "education": [None],
        })
        self.source.to_csv(self.path, index=False)

    def state(self):
        result = {}
        with self.conn.cursor() as cur:
            for table in ("snapshots", "jobs", "job_skills", "users", "captcha_challenges"):
                cur.execute(f"SELECT * FROM {table} ORDER BY id")
                result[table] = cur.fetchall()
        return result

    def test_atomic_replacement_and_repeat(self):
        before = self.state()
        first = run_snapshot(self.conn, self.config)
        after = self.state()
        self.assertEqual({r[1] for r in after["snapshots"]}, {"2018", "2020"})
        for table in ("users", "captcha_challenges"):
            self.assertEqual(after[table], before[table])
        for table in ("jobs", "job_skills"):
            self.assertEqual([r for r in after[table] if r[1] == 1],
                             [r for r in before[table] if r[1] == 1])
            self.assertFalse(any(r[1] == 77 for r in after[table]))
        self.assertEqual([r for r in after["snapshots"] if r[1] == "2018"],
                         [r for r in before["snapshots"] if r[1] == "2018"])
        second = run_snapshot(self.conn, self.config)
        self.assertEqual(first, second)
        repeated = self.state()
        self.assertEqual(repeated["snapshots"], after["snapshots"])
        # 自增岗位 id 可变化，业务内容和其他表保持一致。
        self.assertEqual([r[1:] for r in repeated["jobs"]], [r[1:] for r in after["jobs"]])
        self.assertEqual(repeated["job_skills"], after["job_skills"])

    def test_preflight_failures_preserve_every_table(self):
        before = self.state()
        for stage, error in (("load_csv", OSError("read failed")),
                             ("clean_jobs", RuntimeError("clean failed"))):
            with self.subTest(stage=stage):
                with patch(f"etl.run_etl.{stage}", side_effect=error):
                    with self.assertRaises(type(error)):
                        run_snapshot(self.conn, self.config)
                self.assertEqual(self.state(), before)
        for source in (self.source.iloc[:0], self.source.drop(columns="salary")):
            source.to_csv(self.path, index=False)
            with self.assertRaises(ETLValidationError):
                run_snapshot(self.conn, self.config)
            self.assertEqual(self.state(), before)
        self.config["path"] = str(self.path.parent / "missing.csv")
        with self.assertRaises(FileNotFoundError):
            run_snapshot(self.conn, self.config)
        self.assertEqual(self.state(), before)

    def test_write_failure_preserves_every_table(self):
        before = self.state()
        with patch("etl.repository.insert_jobs", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                run_snapshot(self.conn, self.config)
        self.assertEqual(self.state(), before)

    def test_failure_after_old_deletion_restores_new_and_old(self):
        def delete_then_fail(conn, label):
            remove_snapshot(conn, label)
            raise RuntimeError("after deletion")

        for existing_new in (False, True):
            with self.subTest(existing_new=existing_new):
                if existing_new:
                    with self.conn.cursor() as cur:
                        cur.execute("INSERT INTO snapshots (id,label,source,period,note) "
                                    "VALUES (99,'2020','previous-new','old-period','old-note')")
                        cur.execute("INSERT INTO jobs (snapshot_id,job_name) VALUES (99,'previous-job')")
                        cur.execute("INSERT INTO job_skills (snapshot_id,source_map_id,key_word,skill) "
                                    "VALUES (99,1,'prior','prior-skill')")
                    self.conn.commit()
                before = self.state()
                with patch("etl.repository.remove_snapshot", side_effect=delete_then_fail):
                    with self.assertRaisesRegex(RuntimeError, "after deletion"):
                        run_snapshot(self.conn, self.config)
                self.assertEqual(self.state(), before)
