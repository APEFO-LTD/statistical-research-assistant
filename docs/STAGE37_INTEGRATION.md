# Stage 37 integration branch

Branch `claude/stage37-integration`, built on
`stage37/master-acceptance-interoperability-spec` @ `2f9af71` (the owner's PR #71).
Every feature branch is merged with a merge commit (`git merge --no-ff`); no
branch was rebased, squashed or force-pushed, and no feature branch was changed.

## 1. Merge graph

First-parent history, oldest first. "Parents" are the first parent (the
integration branch before the merge) and the second (the branch head).

| # | Commit | Parents | Merged branch @ head | What it brings |
|---|---|---|---|---|
| 1 | `32c2223` | `2f9af71`, `0a7c742` | `claude/stage37-0b` @ `0a7c742` | Stage 37.0b and its review fixes |
| 2 | `cdded4e` | `32c2223`, `7f35f0a` | `claude/stage37-methods` @ `7f35f0a` | path models, linear model, in-house Cronbach's α; pingouin to the dev lock |
| 3 | `1dceef3` | `cdded4e`, `89e9e5a` | `claude/stage37-export` @ `89e9e5a` | data export (.xlsx, .csv, .sav), Results workbook, reproducibility bundle; pyreadstat |
| 4 | `82be61a` | `1dceef3`, `16a0bdc` | `claude/stage37-rag` @ `16a0bdc` | research library, library questions, packaged FTS5 self-test |
| – | `9218d7a` | `82be61a` | – | CI: Windows path filters for the Stage 37 modules |
| – | `c733d2b` | `9218d7a` | – | this document (part 1) |
| 5 | `8a58344` | `c733d2b`, `b4d9c0c` | `claude/stage37-ux` @ `b4d9c0c` | UX: the one settings file, the shell, the Settings hub, the variable panel and reuse |
| – | `e57adb2` | `8a58344` | – | export defaults and library privacy in the one settings file and the Settings hub (§6) |

All five branches start at `2f9af71` (each `git merge-base` with the base is
`2f9af71`). `claude/stage37-ux` @ `b4d9c0c` already contains
`claude/stage37-ux-shell` @ `6f4ced7` (merge `77cd26c`) and
`claude/stage37-ux-vars` (merges `dcb9207` of `61fa4b8` and `b4d9c0c` of
`c8418ad`). It was merged with one `--no-ff` merge.

## 2. Conflicts and how they were resolved

The rule for every conflict was to keep both sides' content.

| Merge | File | Conflict | Resolution |
|---|---|---|---|
| 2, 3, 4 | `workspace_text.py` | Each branch appended its own `T.update({...})` block after the same line. | Both blocks were kept: the earlier merge's block, then the incoming one. No key is defined in both. A three-way check (`T`, `LABELS`, `PLURALS` of the merged module = base + every branch's changes, with no key changed by two branches) is clean after each merge. |
| 3 | `requirements.txt` | Methods removed pingouin and its dependencies; export added pyreadstat. | Not hand-merged. Both locks were regenerated (§3). |
| 3 | `tests/fixtures/stage37/README.md` | Each branch rewrote the status line. | One integration status line, then the methods increment, then the export increment. The stale "RAG and mediation/moderation are not implemented" was dropped. |
| 3, 4 | `tools/windows_gui_e2e.py` | Each branch appended a 19th journey: its docstring entry, its code after `report-composition` and its `JOURNEYS` entry. | Everything kept, in merge order. No top-level name is defined twice (checked; pyflakes clean). |
| 3, 4 | `tests/test_stage368_review_journeys.py` | Each branch changed the count of journeys (19, or ≥ 18). | The exact combined order is asserted once: `STAGE37_JOURNEYS` after the 18 RC journeys. The branch tests check only their own journey's place: `test_stage37_journey.py` (index 18), and `test_stage37_export_journey.py` / `test_stage37_library_journey.py` (after the 18). |

Merge 5 (`claude/stage37-ux`):

| File | Conflict | Resolution |
|---|---|---|
| `workspace_text.py` | Two hunks: rag's `T.update` block against UX's (variable panel and reuse), and rag's `PLURALS` (documents, passages, pages, statements) against UX's (parts). | Both kept. No key overlap. The three-way check against the base and all five branches is clean. |
| `workspace_analyze.py` | 0b moved `_task_title` to `research_workflow.task_title`, which also takes the run's options. UX added the reuse functions (`duplicate_task`, `repeat_result`, `_start_copy`, `_copy_notice`, state `copied_from`) and changed `_task_title` so that more than three variables read "first … last (N variables)". | UX's reuse functions and 0b's delegation are both kept. UX's naming rule moved into `research_workflow.task_title`, so a task and its results are named by one rule. |
| `tools/windows_gui_e2e.py` | Docstring, journey code and `JOURNEYS` of both sides. Both sides also defined `master_fixture()`: export's writes into the folder given, UX's into `folder / "stage37-master"`. Both use the same generator. | Everything kept, with one `master_fixture()` (export's). The `variable-picker` journey now calls `master_fixture(work / "stage37-master")`, which gives the same files. `open_interpretation` is identical on both sides (export `8be2415`, UX `c8418ad`), so it appears once. |
| `tests/test_stage368_review_journeys.py` | Both sides changed the journey count. | `STAGE37_JOURNEYS` lists the six Stage 37 journeys. `test_stage37_shell_journeys.py` now checks that its three journeys come in order after the 18, not the total count. |
| `app_preferences.py` | UX split `save_preferences` into the settings file (without a path) and `_save_file` (with a path). Export made `save_preferences` keep the keys it does not manage. | UX's split, with export's key preservation inside `_save_file`. The export choices move to the settings file in the next commit (§6). |
| `windows-gui-e2e.yml` (no textual conflict) | `app_preferences.py` was listed twice, once by export and once by UX. | Listed once. |

Journey order: the 18 RC journeys, then `stage37-hypothesis`, `export-data`,
`research-library`, `startup-workspace`, `settings-language`,
`variable-picker` (24).

Auto-merged files changed by more than one branch were reviewed as well:
`project_session.py`, `project_store.py`, `research_workflow.py`,
`workspace_analyze.py`, `workspace_projects.py` and `workspace_shell.py`. The
changes are in different functions. `project_store.SCHEMA_VERSION` stays 6.

A follow-up adjustment that is not a textual conflict: `tests/test_stage37_dependency.py`
(export) expected the export branch's 50 runtime pins. It now expects the integrated 42 and checks that pingouin is not in the runtime lock.

## 3. Locks

The inputs were resolved to the union of both intents. `requirements.in`
(auto-merged) has no pingouin and adds `pyreadstat>=1.3,<2`.
`requirements-dev.in` is the methods version, with pingouin as the test-only oracle.

Both locks were regenerated once with uv 0.11.32, using the exact header commands:

    uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements.txt
    uv pip compile requirements-dev.in -c requirements.txt --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements-dev.txt

The methods runtime lock was in place as uv's preference file, so the pins the methods branch had were kept.

| Lock | vs. methods (`7f35f0a`) | vs. export (`89e9e5a`) | vs. base (`2f9af71`) |
|---|---|---|---|
| `requirements.txt` (42 pins) | + pyreadstat 1.3.7. Every other version, marker and hash is identical. The only other text change is narwhals' "via" comment, which now names pyreadstat too. | − cloudpickle 3.1.2, joblib 1.6.0, pandas-flavor 0.8.1, pingouin 0.7.0, scikit-learn 1.9.1, seaborn 0.13.2, tabulate 0.10.0, xarray 2026.9.0. pyreadstat's 26 hashes are identical, including the cp312 win_amd64 wheel `7b65bd28…4609`. | − the eight above, + pyreadstat 1.3.7 |
| `requirements-dev.txt` (82 pins) | byte-identical | + pingouin 0.7.0 and the 23 packages it brings, at the runtime lock's versions | as vs. export |

Tool checks, in a fresh venv with both locks installed by hash:

- `tools/build_toolchain.py identity --strict`: the host packages match the locks exactly (expected 88, found 88, 0 missing, 0 extra, 0 mismatched). The only deviation is the host Python: 3.12.3 here, while the lock says 3.12.16, which uv could not provide in this container. That deviation comes from the environment, not from the lock.
- `tools/build_sbom.py`: 84 components. pyreadstat 1.3.7 is listed as Apache-2.0, with ReadStat (MIT) inside it. pingouin is gone. The copyleft list (OCR DLLs and certifi only) is unchanged.
- `docs/STAGE368_BUILD_LOCK.md`: the counts were updated (42 runtime and 82 development packages, the package table, the SBOM's Python packages).

## 4. CI workflows

- `python-tests.yml`: the methods change is kept. The unit job installs
  `requirements.txt` and `requirements-dev.txt`, so the pingouin oracle runs, and
  the pruned-runtime job keeps the runtime lock alone.
- `windows-gui-e2e.yml`: export's path triggers are kept. Commit `9218d7a` adds the
  modules the Stage 37 journeys run:
  - 0b: `research_workflow.py`, `research_report.py`, `interpretation_docx.py`, `report_docx.py`.
  - methods: `cronbach.py`, `linear_model.py`, `process_*.py`, `reliability.py`,
    `item_diagnostics.py`, `correlation.py`, `batch_correlation.py`, `analysis_runs.py`,
    `result_store.py`, `interpretation_*.py`.
  - export: `data_preparation.py`.
  - rag: `research_library.py`, `library_ask.py`, `ai_*.py`, `tests/library_fixtures.py`.
- `windows-package.yml`: adds the new top-level modules bundled into the program, plus
  `reliability.py`, `research_workflow.py` and `research_report.py`. The packaged
  self-test runs the in-house α and the FTS5 search.
- `workspace_export.py` and `workspace_library.py` were already covered by `workspace_*.py`.
- Every new top-level module of the four branches is now in a Windows path filter (checked by listing the `*.py` files missing at `2f9af71`).

UX's workflow changes are kept. They include the settings and shell tests on
Windows in `python-tests.yml`, the classic-interface start checks, and the
`user_settings.py` and `window_state.py` path triggers. The UX branch changes neither lock.

## 5. Semantic checks (after each merge)

New test module: `tests/test_stage37_integration.py`, which covers the seams between branches.

| Check | How | Result |
|---|---|---|
| Locale | `tools/locale_audit.py` after every merge | missing 0, placeholder 0 each time. "identical" rose from 0 to 15 with methods: abbreviations SE, SMD and VIF in `process_text.TEXT`, branch content, not caused by the merge. |
| Project format 6, append-only records | `SCHEMA_VERSION = 6` unchanged. 0b's store tests (`protocol_records_no_replace` trigger, update/delete refused) pass on every merged tree. Export keeps metadata in existing format-6 columns, and the library is a separate database in the project folder. | ok |
| K1 confirmation scopes (0b × methods) | `ConfirmationScopeTests`: a conditional-process task's confirmations make 0b's design step ready for Model 7 only. Moving to Model 14 (methods' option-bound scope) or to another mediator clears it. Both branches' own K1 tests pass. | ok |
| Word report (0b × methods) | `WordReportTests`: through the real handlers, H1's correlations plus a Model 4 mediation. The report holds "H1 (primary): …", "result current, in this report.", the evidence table (H1 × 1 result), "Mediation (PROCESS-equivalent Model 4)" and the indirect-effect table. | ok |
| Results workbook (export × methods × 0b) | `ExportTests`: Results → *Save*. The workbook has 4 sheets. Methods' `indirect:m0` and its CI are unrounded, equal to the engine. Provenance carries 0b's hypothesis snapshot (H1's id) and the bootstrap seed and resamples. | ok |
| Bundle report (export × 0b) | the reproducibility bundle's `report/*.docx` holds the hypothesis rows and the path model; the manifest has 2 analyses | ok |
| Library backup choice × export bundle | `LibraryExportTests`: with the library chosen to travel, the data bundle contains nothing of the library while the `.sra` backup contains `project/library/backup.json`. Exporting leaves the backup choice, and changing the backup choice leaves the remembered export choices. | ok |
| Packaged-style self-test | `analysis_selftest.py` on the merged tree: ok, 0 errors. Steps include `alpha` (in-house) and `research_library` (FTS5 and trigram available). | ok |

Targeted tests after each merge (integrated venv; the full suite was not run in part 1):

| After | 0b set | methods set | export set | rag set | common* |
|---|---|---|---|---|---|
| merge 1 | 240 OK (with common) | – | – | – | – |
| merge 2 | 240 OK (with common) | 192 OK | – | – | 3 (integration) OK |
| merge 3 | 174 OK | 192 OK | 84 OK | – | 66 OK |
| merge 4 | 174 OK | 192 OK | 84 OK | 116 OK | 67 OK |
| merge 5 (`8a58344`, merge only) | – | – | 84 OK | – | 68 OK; UX set 117 OK |
| `e57adb2` (reconciled) | 174 OK | 192 OK | 84 OK | 116 OK | 72 OK; UX set 117 OK |

\* common: `test_stage368_review_journeys`, `test_build_lock`, `test_locale_audit`,
`test_localized_guides_apa7` and `test_stage37_integration`. Each branch set has the
branch's new and changed test modules. 0b: `test_stage37_*` of 0b and
`test_workspace_journey_strip`. methods: `test_cronbach`, `test_linear_model`,
`test_process_*`, `test_spearman_floor`, `test_stage37_fixture_v2`,
`test_stage37_master_acceptance`, `test_stage37_methods_fixes`,
`test_distribution_tools`, `test_repeated`, `test_stage36_scales`,
`test_workspace_foundations` and `test_workspace_journeys`. export:
`test_stage37_csv_guard`, `test_stage37_dependency`, `test_stage37_export*` and
`test_app_preferences`. rag: `test_library_*`, `test_research_library`,
`test_stage37_ai_rows`, `test_stage37_library_journey` and `test_workspace_library`.
UX: `test_stage37_settings`, `test_stage37_shell_journeys`, `test_stage37_ux_metrics`,
`test_stage37_variable_panel`, `test_workspace_shell` and `test_app_startup`.
After merge 5 the locale audit still shows missing 0 and placeholder 0. "identical" is 19:
the 15 above plus 4 from the UX branch, none from the integration's own texts.

## 6. Settings reconciliation (commit `e57adb2`)

The two branches kept settings in different places:

- UX keeps every setting in one file, `settings.json` in the data folder
  (`user_settings`). It never writes the files of earlier versions, and it
  keeps Russian.
- Export remembered its choices in `preferences.json` under `"export"`.

Before this commit, the merged program would have gone on writing the old
file that UX promises never to change. What changed:

| Part | Change |
|---|---|
| `user_settings` | New key `export`: `{"formats": {page: format}, "csv_layout", "csv_bom"}`, default `{}`. Its validator is `clean_export`: what this version knows is used, and anything else stays in the file as written, like UX's other keys. `migrate_legacy` copies an earlier build's `preferences.json` `"export"` as written. The language (Russian kept), recent files and style are copied as before. |
| `app_preferences.export_preferences` / `remember_export` | Without a path, they read and write the settings file through `UserSettings` (`update(export=…)` writes only that key, after reading the file again). If the settings file holds no export choices yet, the ones an earlier build left in `preferences.json` are read and carried over at the next save. That covers a settings file made by a UX build before an export build wrote its choices. With an explicit path, the old single-file format works as before. |
| Export cards (`workspace_export`) | They use `app.settings`. `forget_choices(app)` makes them read the choices again after Settings changes them or after *Reset settings*. Export defaults are settings, so a reset clears them. Research data is not touched. |
| Settings → *Export defaults* (order 65) | The format each card (Data, Results, Reports) starts with, the CSV separator (while none is chosen, the caption names the language default) and the byte-order mark. These are the same values the cards remember: a change on a card shows here, and the other way round. A caption says that exports are written only where you save them and never include a research library. |
| Settings → *Research library and privacy* (order 85, after *AI privacy*) | Shows that search is local only, and which backend this SQLite offers (FTS5, or the slower built-in search). Shows the real state of *Ask with sources*: which provider and model are ready (`ai_context.readiness`), or that it is off. For the open project it has the same backup-and-copy choice as the Library page (`research_library.travels`, off by default, with the same note); a change here shows there, and the other way round. Without an open project it says to open one. |
| Texts | 15 new EN/LV/RU keys (LV and RU are drafts for native review). The locale audit shows missing 0 and placeholder 0. |
| e2e | The `export-data` journey and its harness test read the remembered format from the data folder's `settings.json`. |
| Tests | `test_stage37_settings`: the hub's section list now includes `export` and `library`. Its "another feature" test registers its own key instead of replacing the real export section. `tests/test_stage37_integration.py` (`SettingsFileTests`) checks five things. Migration loses nothing and keeps Russian, and the old file stays byte-identical. Remembering a choice leaves the language as it was. The fallback read works. The hub's export section matches the cards' choices in both directions and after a reset. The library section shows and changes the real backup choice. |


## 7. Full suite (once, on the final code)

The suite ran once, on commit `129f0ed`, with:

    SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 python -m unittest discover -s tests

The Python was 3.12.3 in a fresh venv with `requirements.txt` and
`requirements-dev.txt` installed by hash.

**Result:** 1827 tests ran in 1338 s. All passed: **OK, 10 skipped**, 0 failures,
0 errors.

The commit that adds this section changes only this document.

Not run here: the Windows workflows (GUI journeys, package, installer, update).
The six Stage 37 journeys have been checked only in the harness and have not run on Windows.


## 8. Windows journeys of PR #79: root causes

The installer run 43890696464 (commit `8c6afb3`) and the packaged GUI run
43890696377 (same commit) passed 22 of 24 journeys. The installer run
43894133123 (`90d0b40`) failed one more step (project-a). The packaged run
43894133074 (`90d0b40`) failed only the same two. `8c6afb3` and `90d0b40`
have the same product code.

| Journey, step | Root cause | Kind | Fix |
|---|---|---|---|
| `stage37-hypothesis`, "UCLA with the eight scales, Spearman, Run": no *All quantitative (9)* | After *Create the analysis for H1*, U11 put the keyboard focus on the *First variable* dropdown (`autofocus` + `focus()`). Flet's non-editable dropdown gives its field a focus node that refuses focus (`canRequestFocus = editable`). When asked anyway, its open menu ignored the first arrow key. Down×3 therefore chose Sex instead of UCLA. The screenshot says "Sex — already the first variable", and the panel correctly offered *All quantitative (10)*. Once UCLA is the first variable the panel offers *(9)*, so the journey's selector was right. This was reproduced in a real Flutter client (Flet web, Chromium, Playwright): Sex with the request, UCLA without it. In the other journeys the keyboard choice worked and none of them had a focus request. | product | `8d9d0e9`: `WorkspaceApp.can_take_focus` does not treat a non-editable dropdown as a focus target. The request goes to the next control instead (the panel's *Find variables*). |
| `startup-workspace`, "Settings: the classic interface as the start interface": saved `workspace` | The menu of *Interface at start* exposes no entries to UI Automation, so the driver chose by keyboard. UI Automation exposes no value of a Flet dropdown (it read `''`), so the driver counted two Downs from "no entry". Flutter's `DropdownMenu` (material_ui 1.6.0) opens a freshly built dropdown with the shown entry (*Research workspace*) highlighted, so the two Downs wrapped round to it. In Flet web, two Downs keep `workspace` and one Down gives `classic`, so a keyboard user can choose the classic interface. This is not (a), an inaccessible control. It is not (b), a lost update: a choice is saved when it is made, and a new test interleaves the Settings choice, the export cards and a second settings instance. | driver | `890178f`: `keyboard_keys()` counts from the shown entry, and `choose(current=…)` names that entry. The journey passes it. |
| `project-a`, "choose outcome, group and covariate": no *Outcome* (installer run 43894133123 only) | The click on the ANCOVA card in the step before was lost. At the end of "open ANCOVA among all methods" the screenshot shows the method catalogue and Windows' system menu open. The next step closed the menu (`[menu] … closing it`) and found no form. That step checked nothing after its click, so the failure surfaced one step later. **What opened the system menu is not established.** The driver sent no key in that step, the file dialog was filled by a click (no Alt+N), and the program's window guard made 0 interventions. | driver (step without a check); the trigger is unknown | `890178f`: `open_method_form()` waits for the form's first field. If the form is missing, it logs the lost click and whether the system menu is open, closes the menu and clicks the card once more. |

Tests that fail without the fixes: `test_stage37_journey` (focus after
*Create the analysis for H1*), `test_stage37_settings`
(`can_take_focus`), `test_stage37_shell_journeys` (`DropdownKeyboardTests`
and the harness walk with `current=`, and `MethodFormTests`). Evidence only (it
passes before and after): `test_stage37_integration`
(`test_the_start_interface_survives_the_other_writers_of_the_settings_file`).

Full suite after these fixes, run once on `890178f` with the command in §7:
1834 tests ran in 1410 s, **OK, 10 skipped**. These journeys have not run
on Windows again yet.

### 8.1 Journey step time budget (run 43910859452, `16efe4e`)
The packaged GUI journeys step stopped at its 45-minute limit while the 22nd of 24 journeys (`startup-workspace`) was running; the 21 journeys before it had passed. The limit was set for the 18 RC journeys; the six Stage 37 journeys add about 12 minutes on the hosted runner. Both journey steps (packaged program in `windows-gui-e2e.yml`, installed program in `windows-installer.yml`) now have 75 minutes; the job limits (120 and 170 minutes) still cover the build and the other steps. No journey or check was removed or shortened.

### 8.2 Defects found by hand in the installed build (Issue #80, `16efe4e`/`382ac58`)

**P0: `RuntimeError: Frozen controls cannot be updated` in the scales register.**
Flet 1.1.2 semantics (installed package source): the workspace rebuilds the page on every render and puts it in `_page_stack.controls` with the key `workspace-page-<route>`. In `ObjectPatch._compare_lists`, a new object that takes the place of one with the same explicit key is diffed as a frozen pair (`_effective_frozen`: "a non-frozen pair matched by explicit key (different Python objects) must be diffed like a frozen pair"). `_compare_dataclasses` then calls `_dataclass_added(dst, parent, frozen=True)`, and `_configure_dataclass` stamps `_frozen = True` on that object and every control added below it. From then on `Prop.__set__` (`value_types.py`) and `_control_setattr` (`object_patch.py`) raise "Frozen controls cannot be updated", and `BaseControl.update()` refuses the control. The first render of a route is not frozen (another key: remove and add); every later render of the same route is. A change that Flet's client sends (`Session.apply_patch` → `patch_dataclass`) is written into `_values` without the check, so clicks themselves were fine. `WorkspaceApp.render()` called `page.update()` and then `_apply_focus()`, which set `control.autofocus = True` on a control of the page just sent, and so frozen. In the scales register the request was stale: `ScalesCard._add()` called `request_focus("scales-name")` *after* its `render()`, so the next render, the first item box clicked, applied it to the rebuilt name field and raised (the trace of the issue).

Why the tests did not see it: the harness page (`tools/ux_inventory.FakePage`) had a no-op `update()`, so nothing was ever diffed or frozen, and the harness set a clicked control's value with a plain property assignment. `tests/workspace_harness.FletTree` now diffs every `page.update()` and `page.update(control)` with Flet's own `ObjectPatch.from_diff`. It serialises the patch with Flet's own MessagePack encoder, which takes the `__prev_*` snapshots the next diff needs, as the transport does. Clicks and typing reach controls as the client's do (`patch_dataclass`). After a page-wide update, a control on screen that still holds an unsent change (`_dirty`) raises `LostUpdate`. With this harness the existing `RegisterWorkspaceTests` fail at `382ac58` with the issue's exact trace.

Fix (`workspace_shell.py`), a focus transaction: the request is resolved in the tree this render built, `autofocus` is set on it **before** `page.update()` (a new widget takes the focus itself), and `focus()` is requested after it (Flet's method for a mounted control; it changes no property). The request is used up by that render either way. `_add()` makes its request before its render. A non-editable dropdown is still never a target. Nothing is swallowed, nothing is unfrozen, and focus moves are not disabled.

The same class elsewhere (found by the harness, red at `382ac58`):
- *Reports → study title*: `_set_title` changed the preview text in place, which raised once the Reports page had been rendered twice. Now the keyed render follows each keystroke, as for the other fields.
- *Data → Prepare* (the hosted classic panel and `PreparationItems`) is kept between renders and changed in place. When it was opened in a re-render it was added to a frozen page, so it was frozen too and its first change raised. Even when it was not frozen, its in-place changes under the frozen page were never sent: `page.update()` does not diff inside a frozen control, which has no snapshots. Now a page names such *hosted* controls (`hosted_now`). When one enters the page, the page gets a new key once, so it is added as new and not frozen, and the page is then scrolled to the panel. Later renders retain it unmarked (`src is dst`). Its changes are sent with `WorkspaceApp.update_hosted()` (`page.update(control)`). `preparation_ui` takes a `refresh` callable for that and keeps `page.update()` for the classic window.
- Test code and `tools/ux_metrics.py` that assigned values to rendered controls now set them as the client does.

The Windows journey `variable-picker` ends with 22 mouse clicks on the item boxes of the scales register. After each click it waits for the program's own count, it checks that the keyboard focus was not moved to the name field, and it reads the register the program saved in the project database (`events`, kind `scale_register`). `test_stage37_variable_panel.VariablePickerJourneyTests.test_the_walk` walks it in the harness: it raises the issue's RuntimeError at `382ac58` and passes now.

**P1: the legacy-data migration dialog was unreadable on the installed first run.** `data_ui.migration_dialog` chose no colour. Its surface came from the Material theme Flutter resolved (`surfaceContainerHigh` of the dialog), and every text came from the inherited default text style. The two could therefore come from different themes: the classic window's seed theme, the workspace's light or dark theme, or Windows' app mode for "system", which Flutter applies itself. The result was light text on a near-white surface. Now one token palette (`workspace_tokens`) is resolved from the page's theme mode (Windows' brightness for "system") and accent, or passed by the workspace (`ui.p`). The dialog surface (`bgcolor`) and every foreground come from it: title, body, paths, the live status, the italic note, and the button labels in their normal and disabled states. Every text role used is ≥ 4.5:1 on that surface in both themes. The content is width-bounded (≤ 620 px, less in a narrow window, e.g. 175 % scaling) and scrolls, and the actions wrap instead of being clipped. The *Your data* dialogs use the same palette. `tests/test_data_ui.py` computes the contrast of every text and button against the dialog surface (light, dark, system light or dark, no theme; EN/LV/RU; before and after copying). It also migrates a synthetic project, questionnaire and profile: plain files are byte-identical; SQLite databases are copied with SQLite's backup API, so their content (schema, rows, `user_version`) is identical and their header bytes may differ. The originals stay byte-for-byte unchanged. Finally, "Not now" copies, deletes and changes nothing, apart from remembering the answer when asked to. The installed journey `legacy-migration` measures the WCAG contrast of the dialog's title, body and path on its own screenshot (`measured_contrast`, unit-tested on synthetic images). Darkening the backdrop was not used.

Only Windows CI can confirm: the 22 real clicks and the focus check in `variable-picker`, the on-screen contrast in `legacy-migration` (installed program), the dialog at 100–175 % display scaling, and Narrator reading the live status.
