# ============================================================
# test_datavault.py — runs a complete test of DataVault
#
# Run with: python test_datavault.py
# ============================================================

import os
import sys
import shutil
import subprocess

def run(command):
    """Run a datavault command and print it nicely"""
    print(f"\n$ python datavault.py {command}")
    print("─" * 50)
    result = subprocess.run(
        [sys.executable, "datavault.py"] + command.split(),
        capture_output=False
    )

def create_csv(filename, content):
    """Create a test CSV file"""
    with open(filename, "w") as f:
        f.write(content)
    print(f"\n[Created test file: {filename}]")
    print(content)

def modify_csv(filename, content):
    """Modify an existing CSV file"""
    with open(filename, "w") as f:
        f.write(content)
    print(f"\n[Modified: {filename}]")
    print(content)

def tamper_csv(filename):
    """Secretly modify a file to simulate tampering"""
    with open(filename, "r") as f:
        content = f.read()
    with open(filename, "w") as f:
        f.write(content + "\nhacker,injected,this,row")
    print(f"\n[TAMPERED: secretly added a row to {filename}]")

def cleanup():
    """Remove test files and .datavault folder"""
    if os.path.exists(".datavault"):
        shutil.rmtree(".datavault")
    for f in ["training_data.csv", "labels.csv"]:
        if os.path.exists(f):
            os.remove(f)

# ── Run the full test ────────────────────────────────────────

print("\n" + "="*55)
print("   DATAVAULT — FULL WORKFLOW TEST")
print("="*55)

# Clean slate
cleanup()

# 1. Initialize project
run("init my-ai-project")

# 2. Create and add first dataset
create_csv("training_data.csv",
"""id,age,income,label
1,25,32000,0
2,34,54000,1
3,28,41000,0
4,45,87000,1
5,52,95000,1
6,29,38000,0
""")
run('add training_data.csv "raw training data — 6 samples"')

# 3. Add a second file
create_csv("labels.csv",
"""id,label,confidence
1,negative,0.92
2,positive,0.87
3,negative,0.95
4,positive,0.78
5,positive,0.91
""")
run('add labels.csv "initial label set from annotation team"')

# 4. Check status
run("status")

# 5. Modify training data (remove duplicates, fix an error)
modify_csv("training_data.csv",
"""id,age,income,label
1,25,32000,0
2,34,54000,1
3,28,41000,0
4,45,87000,1
5,52,95000,1
6,29,38000,0
7,38,62000,1
8,41,71000,0
""")
run('commit training_data.csv "added 2 new samples, total now 8"')

# 6. Modify again
modify_csv("training_data.csv",
"""id,age,income,label
1,25,32000,0
2,34,54000,1
3,28,41000,0
4,45,87000,1
5,52,95000,1
6,29,38000,0
7,38,62000,1
8,41,71000,0
9,33,49000,0
10,27,35000,1
""")
run('commit training_data.csv "added 2 more samples — dataset now 10 rows"')

# 7. View full history
run("log training_data.csv")

# 8. See diff between v1 and v3
run("diff training_data.csv v1 v3")

# 9. Verify file integrity (should pass)
run("verify training_data.csv")

# 10. Simulate tampering
tamper_csv("training_data.csv")

# 11. Verify again (should FAIL — catches the tampering)
run("verify training_data.csv")

# 12. Restore clean version
run("checkout training_data.csv v3")

# 13. Verify after restore (should pass again)
run("verify training_data.csv")

# 14. Final status
run("status")

print("\n" + "="*55)
print("   TEST COMPLETE")
print("="*55)
print("""
What just happened:
  1. Created a project
  2. Added two dataset files
  3. Committed 2 more versions of training_data.csv
  4. Viewed full history
  5. Compared v1 vs v3 (saw exactly what changed)
  6. Verified file integrity ✓
  7. Simulated a hacker tampering with the file
  8. Verified again — caught the tampering ✗
  9. Restored clean version from vault
  10. Verified again — clean ✓

This is what "data provenance" means in practice.
""")

# Optional cleanup — comment this out if you want to keep the test files
# cleanup()
