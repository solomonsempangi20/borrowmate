# Team plan: four people, four parts

Each member owns a **separate set of files**, so everyone can push to GitHub
without merge conflicts. Sizes are balanced (about 600 to 1000 lines each,
including tests).

> **Important:** the parts depend on each other (the CLI needs the models, and so
> on). So **everyone keeps the full project folder on their computer** to run and
> test the app, but **only `git add` your own files** (listed below). The
> repository becomes fully runnable once all four pull requests are merged, and
> that is expected.

## Who owns what

| # | Part | Branch | Files you push |
|---|------|--------|----------------|
| **1** | **Foundation: models** | `feat/models` | `__init__.py` (root), `.gitignore`, `models/` (all 7 files), `tests/__init__.py`, `tests/helpers.py`, `tests/test_abstraction_polymorphism.py`, `tests/test_models.py` |
| **2** | **Business rules: services** | `feat/services` | `services/` (all 8 files: clock, notifier, repository, loan_manager, community, seed, timefmt), `tests/test_loan_rules.py` |
| **3** | **CLI + loan extensions & ratings** | `feat/cli-extensions` | `cli/` (all 5 files), `main.py`, `plugins/__init__.py`, `plugins/base.py`, `plugins/loader.py`, `plugins/extensions.py`, `tests/test_cli.py`, `tests/test_plugin_discovery.py`, `tests/test_plugin_extensions.py` |
| **4** | **"I Need This" + reports + docs** | `feat/needs-reports-docs` | `plugins/need_requests.py`, `plugins/reports.py`, `tests/test_plugin_needs.py`, `tests/test_plugin_reports.py`, `README.md`, `TEAM_PLAN.md`, `GITHUB_GUIDE.md` |

Ready-made folders for each person are in `team_packages/member1` ... `member4`
(each contains only that person's files, in the right folders).

## Merge order (very important)

Merge pull requests in this order, because each part builds on the previous one:

**Member 1 (models)  ->  Member 2 (services)  ->  Member 3 (CLI + extensions)  ->  Member 4 (needs, reports, docs)**

You can all push your branches and open PRs on day one; just *merge* them in
order. After the last merge, everyone runs `git pull` and
`python -m unittest discover -s tests -t ..` (expect `OK`, 92 tests).

---

## What each person should be able to explain in the demo

1. **Member 1:** abstraction (`Person`, `Item`), inheritance (`Student`/`Admin`, the three item types, the error hierarchy), polymorphism (`role()`, `category()`...), encapsulation (read-only properties, clamped reliability), the `Loan` state machine, enums, `ItemFactory`.
2. **Member 2:** composition (`Community` owns the inventory, loan manager, clock and notifier), the generic `Repository[T]`, dependency injection (clock and notifier passed in), eligibility rules, conflicts (BLOCKED / COMPETING / CLASH), overdue handling, the seed scenario.
3. **Member 3:** how the CLI builds different menus from `capabilities()`, injected input/output, the plugin system (`MenuPlugin`, auto-discovery with `pkgutil` + `importlib`), extension and rating rules.
4. **Member 4:** the "I Need This" flow (all rules checked before anything is created), expiry after 24 hours, the strategy pattern (`TextFormatter` / `CsvFormatter`), and the README.

---

## Suggested commits (small and meaningful)

Make one commit per line (or group two small ones). Prefixes: `feat:` new
behaviour, `test:` tests, `docs:` documentation, `refactor:` cleanup without
behaviour change. Since the code is already written, commit file by file (see
`GITHUB_GUIDE.md`, step 6).

### Member 1: models (`feat/models`)

```
feat: add project skeleton and .gitignore
feat: add BorrowMateError exception hierarchy
feat: add enums for conditions, item/loan/user status, value tier and capability
feat: add Hostel with haversine distance_to
feat: add abstract Person with Student and Admin
feat: add reliability score with clamping and the trust ladder to Student
feat: add abstract Item with Electronics, Book and HouseholdItem
feat: add ItemFactory to create items by kind
feat: add Loan state machine with transition table
feat: add Loan.overlaps() where back-to-back is not an overlap
test: add shared test world and scripted input/output helpers
test: add abstraction and polymorphism tests
test: add encapsulation, hostel distance and item rule tests
test: add loan transition, illegal-move and overlap tests
```

### Member 2: services (`feat/services`)

```
feat: add Clock abstraction with SystemClock and SimulatedClock
feat: add Notifier abstraction with in-app inbox
feat: add generic Repository[T]
feat: add time formatting and countdown helpers
feat: add LoanManager eligibility checks with explained refusals
feat: add BLOCKED conflict with "free from" time
feat: add COMPETING requests and automatic decline on accept
feat: add owner-only accept, hand over and confirm return
feat: update borrower reliability on return
feat: add overdue detection with notifications to both people
feat: add conflict report with severity
feat: add Community facade composing inventory, loans, clock and notifier
feat: add nearby-items search with distance sorting and radius
feat: add demo seed scenario (3 hostels, 6 users, 8 items)
test: add eligibility rule tests
test: add conflict, auto-decline and accountability tests
test: add overdue, notification, distance and search tests
```

### Member 3: CLI + extensions (`feat/cli-extensions`)

```
feat: add aligned text table renderer
feat: add input parsing for numbers and times
feat: add MenuEntry shared by core menu and plugins
feat: add MenuPlugin base class
feat: add pkgutil plugin loader that auto-discovers plugins
feat: add CLI with login and capability-based menus
feat: add list, near, taken, conflicts, overdue and search views
feat: add request, approve, decline, hand over and return actions
feat: add cancel, dispute, list item and pause/resume actions
feat: add notifications, clock and switch-user actions
feat: show friendly "!" messages instead of crashing
feat: add main.py entry point
feat: add loan extension requests with 1-24 hour validation
feat: add owner approve/decline that clears Overdue
feat: refuse extensions that overlap the next confirmed booking
feat: add ratings (once per side after a return) and average lookup
test: add plugin discovery test
test: add extension and rating tests
test: add scripted CLI tests with injected input and output
```

### Member 4: needs, reports and docs (`feat/needs-reports-docs`)

```
feat: add "I Need This" request and offer classes
feat: notify students within the radius when a request is posted
feat: add offers for listed and unlisted items
feat: check all eligibility rules before creating a loan from an offer
feat: list the unlisted item, create a confirmed loan and decline other offers
feat: expire unanswered requests after 24 hours
feat: add abstract Report with the five report classes
feat: add TextFormatter and CsvFormatter (strategy pattern)
feat: add reports menu with CSV export to file
test: add "I Need This" tests (radius, eligibility, expiry)
test: add report and formatter tests
docs: add README with OOP table, Mermaid diagrams and business rules
docs: add TEAM_PLAN with work split and commit guide
docs: add GITHUB_GUIDE for the team
```

---

## Pull request checklist

- [ ] Branch is up to date with `main` (`git pull --rebase origin main`)
- [ ] I ran `python -m unittest discover -s tests -t ..` in my full local copy and it says `OK`
- [ ] I only added files from my own list
- [ ] The PR description says what I did and which menu steps I tried
- [ ] At least one teammate approved
