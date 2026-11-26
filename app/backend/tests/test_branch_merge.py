"""Branch spellings that differ only by capitals/spaces must be ONE branch (merged + kept merged).

Reproduces the live split seen in Team: HYDERABAD / Hyderabad, VIJAYAWADA / Vijayawada / vijayawada,
VISAKHAPATNAM / Visakhapatnam / visakhapatnam — rows written before the save-time normaliser existed,
so they're planted with raw SQL (bypassing it) exactly as they sit in the database today."""
import os
import tempfile
import unittest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = "sqlite:///" + _db

from sqlalchemy import text  # noqa: E402
from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models, branch_norm  # noqa: E402

_n = [0]


def user(db, role, branch):
    _n[0] += 1
    u = models.User(name=f"U{_n[0]}", email=f"u{_n[0]}@t.in", role=role, branch="X", hashed_password="x", is_active=True)
    db.add(u); db.flush()
    db.execute(text("UPDATE users SET branch=:b WHERE id=:i"), {"b": branch, "i": u.id})   # legacy spelling
    return u.id


def case(db, branch):
    _n[0] += 1
    c = models.Case(customer_name=f"C{_n[0]}", account_no=f"A{_n[0]}", branch="X")
    db.add(c); db.flush()
    db.execute(text("UPDATE cases SET branch=:b WHERE id=:i"), {"b": branch, "i": c.id})
    return c.id


class BranchMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        for _ in range(6): user(db, "fos", "HYDERABAD")
        user(db, "manager", "HYDERABAD")                      # Sable Srinivas
        cls.rayudu = user(db, "manager", "Hyderabad")         # Rayudu Suresh — odd spelling
        user(db, "fos", "Hyderabad"); user(db, "fos", "Hyderabad ")
        for _ in range(5): case(db, "HYDERABAD")
        for _ in range(4): user(db, "telecaller", "VIJAYAWADA")
        for _ in range(3): user(db, "telecaller", "Vijayawada")
        user(db, "telecaller", "vijayawada")
        for _ in range(2): case(db, "VIJAYAWADA")
        for _ in range(3): user(db, "telecaller", "VISAKHAPATNAM")
        for _ in range(9): user(db, "telecaller", "Visakhapatnam")   # more rows, but ALL-CAPS wins (house rule)
        user(db, "telecaller", "visakhapatnam")
        for _ in range(4): case(db, "VISAKHAPATNAM")
        for _ in range(3): case(db, "Visakhapatnam")
        user(db, "fos", "Warangal")                            # a genuinely different branch: untouched
        db.commit(); db.close()

    def test_1_merge_existing(self):
        db = SessionLocal()
        rep = branch_norm.merge_case_variants(db)
        moved = {(r["from"], r["to"]) for r in rep}
        for pair in [("Hyderabad", "HYDERABAD"), ("Hyderabad ", "HYDERABAD"), ("Vijayawada", "VIJAYAWADA"),
                     ("vijayawada", "VIJAYAWADA"), ("Visakhapatnam", "VISAKHAPATNAM"), ("visakhapatnam", "VISAKHAPATNAM")]:
            self.assertIn(pair, moved)
        self.assertEqual({b for (b,) in db.query(models.User.branch).distinct()}, {"HYDERABAD", "VIJAYAWADA", "VISAKHAPATNAM", "Warangal"})
        self.assertEqual({b for (b,) in db.query(models.Case.branch).distinct()}, {"HYDERABAD", "VIJAYAWADA", "VISAKHAPATNAM"})
        # The manager who was on the odd spelling now sees the whole branch — staff and cases.
        r = db.query(models.User).get(self.rayudu)
        self.assertEqual(r.branch, "HYDERABAD")
        self.assertEqual(db.query(models.User).filter(models.User.branch == r.branch, models.User.role == "fos").count(), 8)
        self.assertEqual(db.query(models.Case).filter(models.Case.branch == r.branch).count(), 5)
        self.assertEqual(db.query(models.Case).filter(models.Case.branch == "VISAKHAPATNAM").count(), 7)
        self.assertEqual(db.query(models.User).filter(models.User.branch == "VIJAYAWADA").count(), 8)
        self.assertEqual(branch_norm.merge_case_variants(db), [])     # idempotent
        db.close()

    def test_2_new_writes_join_existing_branch(self):
        branch_norm.install()
        db = SessionLocal()
        u = models.User(name="New", email="new@t.in", role="fos", branch="  vijayawada ", hashed_password="x")
        c = models.Case(customer_name="N", account_no="N1", branch="Vijayawada")
        db.add_all([u, c]); db.commit()
        self.assertEqual(u.branch, "VIJAYAWADA")
        self.assertEqual(c.branch, "VIJAYAWADA")
        u.branch = "warangal"; db.commit()
        self.assertEqual(u.branch, "Warangal")
        n = models.User(name="N2", email="n2@t.in", role="fos", branch=" Nellore ", hashed_password="x")
        db.add(n); db.commit()
        self.assertEqual(n.branch, "Nellore")                   # genuinely new branch: kept, trimmed
        db.close()


if __name__ == "__main__":
    unittest.main()
