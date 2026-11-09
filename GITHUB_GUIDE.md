# GitHub guide: how our team pushes BorrowMate

Read your own part in [TEAM_PLAN.md](TEAM_PLAN.md) first. Members are numbered 1 to 4.
Replace `YOUR-USERNAME`, `REPO-URL` and the branch name with your own values.

## 0. One-time setup (everyone)

1. Install **Git**: https://git-scm.com/downloads (on Windows, accept the defaults; it gives you *Git Bash*).
2. Create a free account at https://github.com.
3. Tell Git who you are. Use the **same email as your GitHub account**:
   ```bash
   git config --global user.name  "Your Full Name"
   git config --global user.email "you@example.com"
   ```
4. Check it works: `git --version`

## 1. Team leader (Member 1): create the repository

1. On GitHub click **New repository**. Name it `borrowmate` (use this exact name, lower case).
   Choose **Private**. Do **not** tick "Add a README" or ".gitignore" (we already have them). Click **Create**.
2. Go to **Settings -> Collaborators -> Add people** and invite the other three by their GitHub usernames. They must accept the email invitation.
3. (Recommended) **Settings -> Branches -> Add rule** for `main`: tick *Require a pull request before merging*. This stops accidental direct pushes.
4. Send the team the repository URL (the green **Code** button, HTTPS), e.g. `https://github.com/YOUR-USERNAME/borrowmate.git`.

## 2. Everyone: keep a full copy to run and test

Make two separate folders on your computer, for example:

```
~/borrowmate-work/
├── full/borrowmate/     <- unzipped borrowmate.zip: the WHOLE project (to run and test)
└── repo/borrowmate/     <- your clone of the GitHub repository (only what you push)
```

Unzip `borrowmate.zip` into `full/`. Open a terminal inside `full/borrowmate` and check that it works:

```bash
python main.py                                   # try the app
python -m unittest discover -s tests -t ..       # expect: OK (92 tests)
```

> Both folders must be named exactly `borrowmate`. The test command needs a valid
> Python name for the project folder; a name like `borrow-mate` (with a dash) breaks it.

Inside the zip there is a `team_packages/` folder with `member1` ... `member4`.
Each contains **only that person's files**, already in the right sub-folders. That
is what you copy into your clone and push.

## 3. Member 1 pushes FIRST (creates `main`)

Member 1 pushes their own files so that `main` exists. (Everyone, including Member 1,
pushes **only their own files**, so GitHub shows each person's contribution.)

```bash
cd ~/borrowmate-work
mkdir repo && cd repo
git init borrowmate && cd borrowmate
cp -r ../../full/borrowmate/team_packages/member1/. .
git status                       # should list only Member 1 files

git add __init__.py .gitignore
git commit -m "feat: add project skeleton and .gitignore"
git add models/errors.py models/__init__.py
git commit -m "feat: add BorrowMateError exception hierarchy"
git add models/enums.py
git commit -m "feat: add enums for conditions, item/loan/user status, value tier and capability"
git add models/hostel.py models/person.py
git commit -m "feat: add Hostel, abstract Person with Student and Admin"
git add models/item.py models/loan.py
git commit -m "feat: add Item hierarchy, ItemFactory and Loan state machine"
git add tests
git commit -m "test: add helpers, abstraction, encapsulation and loan state machine tests"

git branch -M main
git remote add origin REPO-URL
git push -u origin main
```

If Git asks you to log in: use your GitHub username and a **Personal Access Token**
as the password (GitHub -> Settings -> Developer settings -> Personal access tokens ->
*Tokens (classic)* -> tick `repo`). Normal passwords no longer work.

> If you turned on branch protection (step 1.3), switch it off just for this first
> push, then turn it on again.

## 4. Members 2, 3 and 4 (and Member 1 for later changes): push your part

Do this **after** Member 1's first push.

### Step 1: clone the repo and make your branch
```bash
cd ~/borrowmate-work/repo
git clone REPO-URL            # creates the folder  borrowmate
cd borrowmate
git checkout -b feat/services         # YOUR branch name, see TEAM_PLAN.md
```
Branch names: Member 2 `feat/services`, Member 3 `feat/cli-extensions`, Member 4 `feat/needs-reports-docs`.

### Step 2: copy ONLY your files into the clone
Copy the contents of your package folder, keeping the sub-folders. Example for Member 2 (Mac/Linux/Git Bash):
```bash
cp -r ../../full/borrowmate/team_packages/member2/. .
```
On Windows you can also drag the folders into the repo folder and choose *Merge*.

Check: `git status` must show **only your files** as untracked. If you see others, delete them from the clone.

### Step 3: commit in small steps
Use the messages listed for you in `TEAM_PLAN.md` (prefixes `feat:`, `test:`, `docs:`, `refactor:`). Example for Member 2:
```bash
git add services/__init__.py services/clock.py
git commit -m "feat: add Clock abstraction with SystemClock and SimulatedClock"
git add services/notifier.py
git commit -m "feat: add Notifier abstraction with in-app inbox"
git add services/repository.py services/timefmt.py
git commit -m "feat: add generic Repository[T] and time helpers"
git add services/loan_manager.py
git commit -m "feat: add LoanManager eligibility, conflicts, accountability and overdue handling"
git add services/community.py
git commit -m "feat: add Community facade composing inventory, loans, clock and notifier"
git add services/seed.py
git commit -m "feat: add demo seed scenario (3 hostels, 6 users, 8 items)"
git add tests/test_loan_rules.py
git commit -m "test: add eligibility, conflict, overdue and search tests"
```
Rules: always `git add <specific files>` (never `git add .` in the shared repo), and keep each commit small and described.

### Step 4: push your branch
```bash
git push -u origin feat/services
```

### Step 5: open a Pull Request
1. Open the repo on GitHub. Click the yellow **Compare & pull request** banner.
2. Title, for example: `feat: add services (business rules)`. Description: what you added and what you tried.
3. Click **Create pull request**, then choose a teammate under *Reviewers*.

### Step 6: review and merge (in the agreed order!)
- Reviewer: open **Files changed**, leave comments, then **Review changes -> Approve**.
- Author: when approved, click **Merge pull request -> Confirm merge**.
- Merge order: **Member 1 -> 2 -> 3 -> 4**.

### Step 7: check everything after the last merge
```bash
cd ~/borrowmate-work/repo/borrowmate
git checkout main
git pull origin main
python -m unittest discover -s tests -t ..        # expect OK (92 tests)
python main.py
```
This works because the clone folder is named `borrowmate`.

## 5. Everyday Git cheat sheet

| I want to... | Command |
|---|---|
| See what changed | `git status` |
| See history | `git log --oneline` |
| Get teammates' latest work | `git pull origin main` |
| Keep my branch up to date | `git checkout feat/yours` then `git pull --rebase origin main` |
| Undo `git add` for a file | `git restore --staged file.py` |
| Fix my last commit message (not pushed yet) | `git commit --amend -m "new message"` |
| Switch branch | `git checkout branch-name` |

## 6. Common problems

- **`rejected ... fetch first`** when pushing: someone pushed before you. Run `git pull --rebase origin main`, then push again.
- **Merge conflict**: only happens if two people edited the same file. Open the file, keep the correct lines (delete the `<<<<<<<`, `=======`, `>>>>>>>` markers), then `git add file`, `git rebase --continue`. If unsure, ask the file's owner (see TEAM_PLAN.md).
- **`ModuleNotFoundError: models`** or similar: you are running the tests from the wrong folder, or you have not copied/pulled all parts yet. Stand inside the `borrowmate` folder.
- **Tests fail only on `main` before all PRs are merged**: expected. The app needs all four parts.
- **I added a wrong file**: `git restore --staged <file>` before committing. If already committed but not pushed: `git reset --soft HEAD~1`.
- **Never** force-push (`git push -f`) to `main`, and never commit files you do not own.

## 7. Final team check

- [ ] All four PRs merged, `main` has everyone's commits (see **Insights -> Contributors** on GitHub)
- [ ] `git pull` then `python -m unittest discover -s tests -t ..` prints `OK`
- [ ] `python main.py` runs and the README walkthrough works
- [ ] Each member can explain their own part (see TEAM_PLAN.md)
