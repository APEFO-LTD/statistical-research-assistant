# Stage 37.1 — Export and interoperability (Issue #67)

Branch `claude/stage37-export`, from `stage37/master-acceptance-interoperability-spec` (`2f9af71`). Scope: `docs/STAGE37_NEXT_SPEC.md` §2, plus the independent review's findings D8, M2, H2 and its `.sav` requirements (`docs/STAGE37_FABLE_NARROW_REVIEW.md` on `claude/stage37-review`). Synthetic data only: the 180-case master fixture (`tests/fixtures/stage37/generate_master_fixture.py`, generated into a temporary folder by every test) and invented adversarial values.

An item is **done** only when a named test proves it (§9). The Windows journey `export-data` is written and walked in the harness; it has **not** run on Windows in this branch (§8).

## 1. What the researcher sees

One **Export** card on each of three pages. It holds a format (the last one used is remembered), one button that opens the system's Save dialog, and *Advanced options*, folded away.

| Page | Formats (default first) | Default output |
|---|---|---|
| Data | `.xlsx` with codebook · `.sav` · `.csv` · bundle `.zip` | a copy of the data: sheets Data, Codebook, Scales. Exact unless the card lists values the format cannot hold (§2.1); then CSV is offered as the exact copy. No report is needed. |
| Results | results `.xlsx` · bundle `.zip` | every result; *Advanced*: all, the one on screen, or those in the report |
| Reports | bundle `.zip` · results `.xlsx` | data, codebook, results, the Word report as composed, figures, manifest |

- **Two actions at most.** With the remembered format, a click on the button opens the Save dialog. Choosing another format first is the second action.
- **Remembered.** The format per page, the CSV separator and the byte-order mark are kept in `preferences.json` under `"export"` (`app_preferences.export_preferences`, `remember_export`). `save_preferences`, which the classic interface also uses, now keeps keys it does not manage, so a language change there no longer drops them.
- **Before saving**, the card shows:
  - for `.sav`, what the format cannot hold, and every renamed, cut or converted field (see §3.3);
  - for `.xlsx` (and the bundle), every value the format cannot hold exactly, per variable and reason with a count, and *To keep every value exactly, export CSV (.csv)* (`export-xlsx-changes`, review X2);
  - for `.csv`, the formula protection (§5.1);
  - for every row-level export, the columns that may identify participants (§5.4), with *Nothing is uploaded: the file is written only where you choose.*
- **After saving**, the card and the status line name the full path and what was checked, for example *Saved and checked: …\synthetic_master_research_n180.xlsx. Re-opened with an independent reader: 180 rows, 98 variables (xlsx (zip)).* When the .xlsx format changed values, the outcome adds *Not an exact copy: N value(s) were changed for the .xlsx format, as listed before saving (columns). Export .csv to keep them exactly.*
- **Progress.** Large tables are written row by row (openpyxl write-only mode, CSV row writer). The status line shows *Writing row 50,000 of 100,000…*, at most every 0.5 s.
- **Languages.** Every text is in EN/LV/RU (`workspace_text.T`, 87 keys under `export.*` and `data.opt.user_missing*`, 16 of them added by the review fixes). LV and RU are drafts for native review. In Latvian or Russian the CSV separator starts as the semicolon (§3.2).

Data keys: `export-{data|results|reports}`, `export-format-…`, `export-save-…`, `export-advanced-…`, `export-feedback-…`, `export-section-{name}`, `export-csv-layout`, `export-csv-bom`, `export-scope`, `export-bundle-report`, `export-sav-limits`, `export-sav-changes`, `export-xlsx-changes`, `export-csv-note`, `export-sensitive`, `export-blocked-…`; on the Data page `data-opt-user-missing` and `label-{variable}`. No existing key or text was changed.

Code:
- `data_export.py`: formats, codebook, SPSS names, verification, atomic save, participant check. No Flet.
- `export_bundle.py`: codebook from the session and the project, results workbook, provenance, manifest, R syntax, bundle. No Flet.
- `workspace_export.py`: the card.
- `csv_safety.py`: the formula rule, shared with the importer.

## 2. Formats: what each carries and what it loses

### 2.1 `.xlsx` (openpyxl 3.1.5, write-only)

Sheets, each selectable under *Advanced*:

- **Data**: one row per case, the header in row 1 (frozen).
- **Codebook**: one row per variable (columns in §4), then the derived-variable history.
- **Scales**: questionnaire scales, scores made in Data → Prepare, groups made from a scale; the reverse-keyed variables.
- **Results**: an overview, then one sheet per analysis (§2.4).
- **Provenance**: the export's identity (program version, time, dataset, rows, variables, dataset SHA-256) and one row per result.

| Value | Written as | Read back (openpyxl) |
|---|---|---|
| number | a number. A whole number below 2⁵³ as an integer | the same number; whole numbers as `int` |
| a number that needs 17 significant digits (`0.1 + 0.2`) | the shortest text that reads back as the same double (`repr`; openpyxl's own `%.16g` is replaced while writing, review X3) | exactly the same double |
| ±∞, an integer above 2⁵³ | text (a spreadsheet cannot hold them), **listed before saving** | text |
| date, date-time, time from 1900-03-01 | a spreadsheet date with its format | `datetime` (a date at midnight), `time` |
| date or date-time **before 1900-03-01** | **ISO text**, listed before saving (review X1): the 1900 date system has no earlier dates (openpyxl would write 0 or a negative serial, read back as a time), and serials 1–60 mean other days in LibreOffice (Excel's 1900-02-29 that never was) | text |
| date-time with a fraction of a second a serial cannot hold | the date-time, listed (*lose a fraction of a millisecond*) | within 1 ms |
| date-time with a time zone, duration | ISO text / text, listed | text |
| text, including `001`, `=1+1`, `@x` | a text cell: `data_type = "s"`, an inline string. **Never a formula**: the sheet XML has no `<f>` element | the same text |
| empty text `""` | a text cell with no characters (`t="inlineStr"`) | `None` with `data_type "inlineStr"`. A missing value has no cell at all (`data_type "n"`): the two stay distinct |
| missing (NaN, None, NaT) | no cell | `None` |
| user-missing code (−9, DK) | the code itself, never blanked; listed in the Codebook | the code |
| category | its label as text; the order is in the Codebook | text |
| control characters XML cannot hold (C0 controls, lone surrogates, U+FFFE/U+FFFF) | U+FFFD, **listed before saving** | — |
| text over 32,767 characters | cut (the Excel limit), **listed before saving** | — |

More than 1,048,575 rows do not fit in one worksheet. The export says so and writes nothing.

**Never called exact when it is not** (review X2, integrity F1). `data_export.plan_xlsx` lists every value of the Data sheet that the format cannot hold exactly, per variable and reason with a count (`cleaned`, `cut`, `big_integer`, `infinity`, `old_date`, `timezone`, `duration`, `time_precision`, and `name_cleaned`/`name_cut` for a column name). The card shows the list before saving with CSV as the exact alternative, the outcome repeats it, the bundle's manifest lists it under `limitations`, and the export's facts hold it (`changes`, `changed_cells`). The check after writing (§5.3) compares every data cell with the value written: a changed cell must hold exactly its planned replacement and is counted; any other difference fails the save.

### 2.2 `.csv` (UTF-8)

| Property | Rule |
|---|---|
| Layout | **comma** (`,` and a decimal point), or **semicolon** (`;` and a decimal comma). Excel set to Latvian or Russian opens the semicolon file in columns (review H2). Default: comma in English, semicolon in Latvian and Russian; the choice is remembered |
| Byte-order mark | on by default (Excel then shows ā, č and ж); can be switched off |
| Numbers | unquoted. Whole numbers without a decimal point; other numbers with every digit Python needs to read the same double back (`repr`). In the semicolon layout, a decimal comma |
| Texts | always quoted (`csv.QUOTE_STRINGS`). `""` is an empty text; an unquoted empty field is a missing value |
| Formula protection | §5.1 |
| Codebook | written next to the file as `<name>_codebook.json`, with the CSV's SHA-256, layout, decimal mark and the protection rule |

Lost or changed in CSV:
- type information (all text). The codebook says which columns are text.
- the difference between `""` and missing for readers that do not see quotes (pandas reads both as NaN).
- dates become ISO text.
- the program's own importer normalises a lone carriage return in a text to a line feed, as it does for every CSV.

### 2.3 `.sav` (pyreadstat 1.3.7 / ReadStat)

**Carried:**
- values: doubles exact; strings in UTF-8 with any width (long strings above 255 bytes are split by ReadStat);
- variable labels, value labels, measurement levels (confirmed level: nominal, ordinal and scale as such, identifier as nominal, unknown as unknown);
- user-missing values: at most three codes, or one range and one code;
- dates (DATE11), date-times (DATETIME20), times (TIME8);
- numeric display formats (`F8.0` for whole numbers, enough decimals otherwise: display only, the stored doubles are exact);
- the file label;
- notes: the export's identity, the dataset SHA-256, and the original name of every renamed variable.

**Converted, and listed in the preview before saving** (`plan_sav` → `export-sav-changes`):
- **Names.** At most 64 UTF-8 bytes, first character a letter, no reserved word (`ALL AND BY EQ GE GT LE LT NE NOT OR TO WITH`, any case), unique without regard to case.
  - **Short names** (the 8-byte names of the variable records). ReadStat cuts the long name to 8 bytes on a character boundary and upper-cases ASCII letters only, and checks uniqueness byte for byte, so `Возраст` and `возраст_группа` both got `Возр`/`возр`, which SPSS and PSPP compare without regard to case and rename (review SAV-2). After writing, `data_export.unique_short_names` replaces each clashing short name in place by `V` and a base-36 number of the same byte length, in the variable record, the long-names record (7/13) and the very-long-string record (7/14). Long names are not changed. Segment names of very long strings are left as ReadStat writes them (SPSS reassembles by them).
  - A valid name is kept, Latvian and Russian letters included.
  - Otherwise each run of characters SPSS refuses becomes `_`, and `V_` is put in front of a name that does not begin with a letter or is a reserved word. The name is cut at 64 bytes on a character boundary. A clash gets `_2`, `_3`…
  - The rename table is reversible (`restore_names`). It is in the codebook (`spss_names`), and in the file's notes as `Renamed: NAME = original`, or as `Renamed: NAME =` followed by `+ ` lines when the original is longer than one 80-byte note line. The program's importer reads the notes and gives the original names back.
- **Labels** cut at 256 bytes, value labels at 120 bytes, the file label at 64 bytes, always on a character boundary.
- **Identifiers** (confirmed level *identifier*) are string variables, even when their codes are numbers.
- **Categories** (a pandas categorical, such as groups made from a scale) are codes 1…k with value labels, ordinal when ordered.
- **Booleans** are 0/1 with labels False/True.
- **Missing texts.** A text column with missing values gets `""` declared missing: SPSS has no missing value for texts, and declaring the blank keeps it missing. Empty texts and missing texts are then the same.
- **Missing codes beyond the format's limit.** More than three codes are folded into one range and one code when no valid value lies in the range; otherwise the rest are reported as not declared.
- **String codes longer than the variable.** pyreadstat sizes a string variable by its longest value in UTF-8 bytes (and value-label codes by their characters), and a reader compares only the first *width* bytes of a code: `N/A` declared for a width-1 variable would make `N` missing (review SAV-1). Such missing codes are not declared, and such value labels are left out (SAV-6); both are listed (`export.change.missing_width`, `export.change.value_label_width`).
- **Other conversions:**
  - mixed number/text columns become text;
  - a text variable confirmed as *scale* is written as nominal;
  - times with a time zone are converted to UTC;
  - integers above 2⁵³ lose digits.

**Not carried, said in the card and here:** the project's audit trail, the derived-variable history, the analysis provenance, hypotheses and protocol records. They are in the codebook (`.xlsx`, `.json`) and the bundle.

### 2.4 Results workbook (`.xlsx`)

- **Results** sheet: one row per analysis (number, title, method, dataset, rows, complete cases, time, sheet).
- **One sheet per analysis:**
  - title, method, dataset, rows, the time it was calculated, complete cases, needs-review reasons;
  - the verified estimates as shown (parameter, estimate, 95 % CI, p);
  - every result table as shown. Cells are display text, never parsed into numbers;
  - **engine values**: every number of the engine's result object at full precision, as numbers (for example `coefficient`, `p_value`, `coefficients[SYN_LON_TOTAL].se`). Arrays of participants' values are left out;
  - the assumption checks with the researcher's review state, the limitation, cautions and the researcher's note.
- **Provenance** sheet, one row per result: result number, title, method key, options (JSON), variables (JSON), measurement levels (JSON), confirmations, dataset, dataset SHA-256, rows, complete cases, time, restored or not, needs review, saved run id, hypothesis snapshot, seeds (JSON), engine, report SHA-256.

A result restored from a project gets its engine object back first (`ProjectBinding.ensure_result`). When it cannot be recalculated, its sheet says that the engine values were not kept, and the shown estimates are its record.

### 2.5 Reproducibility bundle (`.zip`)

| Member | Content |
|---|---|
| `manifest.json` | format and version; time; program version, channel, build, commit; library versions (`project_store.library_versions`); project title and id; the dataset (name, rows, variables, **SHA-256 of the table as CSV text, as every result records it**); per analysis: method key and title, options, roles, confirms, confirmations, dataset SHA-256, rows, complete cases, levels, time, restored, needs review, saved run id, hypothesis, **seeds**, report SHA-256, syntax; every file with SHA-256, size and description; privacy (row-level data: yes; uploaded: no; possibly identifying columns); format notes; limitations |
| `data/<name>.csv` | comma layout, no byte-order mark, formula-protected (`data_file` in the codebook) |
| `data/<name>_codebook.json` | the codebook again, next to the CSV, where the program's importer looks for it: the bundle's CSV opens with its exact texts (review F5) |
| `data/<name>.xlsx` | Data, Codebook, Scales |
| `data/<name>.sav` | the `.sav` of §2.3 (when it cannot be written, the manifest says why) |
| `codebook/codebook.json` | the complete codebook (§4), with the rename table |
| `results/results.xlsx` | §2.4 with Provenance |
| `report/<name>.docx` | the Word report as composed on the Reports page, when there is one and it is not blocked by outdated results (can be left out under *Advanced*) |
| `figures/R<n>_<section>.png` | the figure of each result as shown |
| `figures/R<n>_<section>_view.svg` | the researcher's Chart Studio view of a result, as SVG with its text alternative, when one exists |
| `syntax/R<n>_<method>.R` | R syntax, only for the verified methods (§2.6) |

**Seeds.** The bundle records three kinds:
- the seeds and resampling counts the engine keeps in its result objects or structured provenance (`seed`, `resamples`, `permutations`);
- the seeds fixed inside engine functions that do not keep them (`export_bundle.ENGINE_SEEDS`): Spearman's permutation p (seed 2026, 1,999 resamples) and parallel analysis (seed 20261103, 150 simulations). A test checks that the engine still uses them;
- the engine's own p-method text when it names a seed.

### 2.6 R syntax (only where verified)

| Method | R code | Check values compared with the engine |
|---|---|---|
| Pearson correlation | `cor.test(x, y, method = "pearson")` | r, p, CI low/high, n |
| Linear regression without HC3 | `lm()` + `summary()` | R², adjusted R², F, n, and b, SE, p of every term |
| Welch t (two groups) | `t.test(y ~ g, var.equal = FALSE)`, the groups in the engine's order | t, df, p |
| One-way ANOVA / Welch ANOVA | `oneway.test(y ~ g, var.equal = TRUE/FALSE)` | F, df1, df2, p |

- Each script reads the bundle's CSV **with every column as text** (`colClasses = "character"`), as the program keeps it: group codes such as `01` and `02`, or `1` and `01`, stay distinct as in the engine (review integrity F2; `read.csv` used to turn them into the numbers 1 and 2, so Welch stopped and ANOVA merged two groups). Numbers are converted with `type.convert`. It removes the protection of rule v2 from the column names and from group texts (`unprotect`, a PCRE `gsub` equal to `csv_safety.restore`, tested on 600 random texts), so a variable named `-y` is found (review F6). It prints the R output and the check values; the manifest holds the engine's values for the same names.
- **Verification:** `test_the_r_syntax_reproduces_the_engine` runs every script with Rscript (R 4.3.3 here) on an unpacked bundle of the fixture. All **29 check values** agree with the engine to 1e-9 relative. `test_r_syntax_reproduces_text_coded_groups_and_protected_names` does the same for Welch on `01`/`02`, ANOVA on `1`/`01`/`2`, Pearson with `-y` and Welch on the groups `=a`/`-b`. The tests are skipped when Rscript is not installed (`skipUnless`).
- Every other method gets **no syntax**. The manifest gives the reason, for example *no verified syntax for this method in this version*. This covers Spearman (its p is a permutation estimate R would not reproduce), Mann–Whitney, chi-square, Kruskal–Wallis, paired tests, reliability and factor analysis.
- **SPSS syntax is not generated.** No SPSS or PSPP run could verify it in this branch.

## 3. Variable metadata (review M2) and `.sav` import

### 3.1 In the data model

`workspace_state.VariableInfo` has four new fields with defaults:
- `label`;
- `value_labels`: (code, label) pairs;
- `missing_codes`: codes as text, or `("range", lo, hi)`;
- `metadata_source`: `sav`, `codebook` or `project`.

They are documented metadata only, never inferred. They come from a `.sav` file, from the codebook of a CSV this program exported, or from the project. Questionnaires still give labels, value labels, missing options, reverse keys and scale ids for their own question keys.

- They belong to the **dataset they came with** (review integrity F3). They stay for a prepared version of the table on screen and for a re-import of the same content (the table's SHA-256), never for another file because it has the same column names: a later table starts without them and gets its own file's metadata only (`set_metadata(…, replace_all=True)`). Confirmed levels still carry over by column, as before.
- `ResearchSession.set_metadata` applies them. A level the file documents becomes the **suggested** level only; the researcher still confirms it.
- The Data page shows a label under the variable's name (`label-{variable}`).

There is **no editor** for labels, value labels or missing codes in this increment. They are imported from `.sav` and from the exported codebook, and taken from questionnaires.

### 3.2 In the project: format 6, no new column

`Project.save_variable_metadata` and `variable_metadata` store the metadata without a schema change. `SCHEMA_VERSION` stays 6, and the test checks it.
- Each label goes in **`variables.label`**: a format-6 column that nothing wrote before.
- Value labels and missing codes for each variable go in one JSON document in **`datasets.notes`**: also unused before, marked `"format": "sra-variable-metadata"`. Notes that hold anything else are never overwritten: the save is refused in words.
- `ProjectBinding` saves them on change and with every new dataset version, and restores them with the dataset. They therefore travel in `.sra` backups and duplicates like the rest of the database.

### 3.3 `.sav` import

`data_loader.load_dataset_with_report` reads `.sav` and `.zsav` with `pyreadstat.read_sav(user_missing=True)`. The Data page's Open dialog lists them.
- **Labels, value labels, missing codes and measurement levels** come in as `ImportReport.metadata`.
- **User-missing values** are, by default, *missing* in the table, as SPSS treats them, and their codes stay declared with the variable. Import option *SPSS user-missing values → Keep the codes as values* (`ImportOptions(user_missing="codes")`, `data-opt-user-missing`) keeps −9 or DK as values instead, for an exact round trip. The import report then tells the researcher to mark them missing before analysing.
- Blank texts are missing, as in every other import.
- A file this program exported gets its **original variable names** back from its notes.
- **windows-1251/1257 long names with the byte 0xFF** (`я`, `˙`): ReadStat refuses such a long-names record (its name grammar expects UTF-8, where 0xFF never occurs) and the file did not open (review SAV-3). The importer then reads the file with that record set aside (`_read_sav_without_long_names`: its subtype is changed in memory, ReadStat skips records it does not know) and decodes the long names itself with the file's declared encoding. The import report says so.

## 4. The codebook

One row per variable, in `.xlsx`, `.json` and the bundle:

- variable name and SPSS name;
- full label and where it came from;
- measurement level (confirmed), where it was confirmed, the suggested level;
- storage (kind and dtype);
- value labels, user-missing codes and where they are defined;
- valid values or the observed range. An identifier's or free text's values are never listed, only their number;
- counts: valid, missing (empty cell), user-missing, empty text, distinct;
- reverse-keyed, scales, the derivation rule and notes.

Then the **derived-variable history**, oldest first: step, kind, outputs, inputs, parameters (JSON), recorded at, dataset. It is collected along the dataset's lineage in the project (every version back to the imported one) and from steps the session has not saved yet.

Sources:
- the data file's metadata (§3), first;
- the questionnaire: wording, value labels or Likert anchors, missing options (DK/PNA) for `…__missing_reason` columns, reverse keys, scale ids;
- Data → Prepare: reverse items, scale scores (method, minimum answered), missing codes (`mark_missing` declares its codes on the source column);
- groups from a scale: rule, bounds and labels, the statement on documented cut points.

## 5. Security and privacy

### 5.1 Formula injection in CSV (OWASP "CSV Injection")

- Rule `owasp-separator-apostrophe-v2` (review F1-separator-split, F3). A cell can start at the beginning of a text and, for a reader that splits on another separator (Excel splits a `.csv` on the Windows list separator, `;` in Latvian and Russian settings) or ignores quotes, after every `,` `;` tab, carriage return or line feed. At each such place, after any spaces and double quotes, a text that begins with `=`, `+`, `-`, `@`, their full-width forms `＝ ＋ － ＠`, a tab, a carriage return or a line feed gets **one apostrophe in front** (`csv_safety.protect`): `ok;=1+1` is written `ok;'=1+1`, ` =x` is written ` '=x`. Column names too.
- So does a text that has apostrophes followed by one of those characters there, which makes the rule **reversible** for every text: `restore(protect(t)) == t` (tested on 4,000 random strings and the edge cases; an apostrophe is never a separator, space or quote, so adding one never moves a place where a cell can start). Files of the first rule (`owasp-leading-apostrophe-v1`) are restored with that rule.
- Every text is quoted, so a separator, quote or line break inside a text cannot start a new cell for a reader that honours quotes. A non-finite number is written as protected text, never as a bare `-inf` (review F7).
- **Numbers are never changed**: −5 in a numeric column is written `-5`, unquoted.
- The program's importer removes the apostrophe **only** when the codebook (or Data → Prepare's transformation log) next to the CSV vouches for exactly this file: format marker, rule and SHA-256. In any other CSV, and in an exported CSV edited afterwards, an apostrophe is the researcher's own text and stays.

Both interfaces export questionnaire responses with one function, `survey_storage.export_survey_responses`, which writes the CSV and the codebook that records its format marker and SHA-256. Before, the classic Survey panel (the default interface) wrote a codebook without them, so its protective apostrophes stayed on import (review F2).

**Review D8**, the first commit (`2ef9110`). The two CSV exports that existed before wrote text cells unescaped: questionnaire responses (`survey_storage.save_survey_csv`) and the prepared dataset (`data_preparation.save_prepared_dataset`). Both now protect text cells and column names. Their codebook or log records the file's SHA-256, so the program reads them back exactly. `tests/test_stage37_csv_guard.py` was written first and failed (red); it passes with the guard.

### 5.2 Spreadsheets
- Every text cell in `.xlsx` is written explicitly as a string (`data_type = "s"`).
- No cell can be a formula: the tests search the sheet XML for `<f>`.
- The importer already never evaluates formulas.

### 5.3 Files
- **Atomic save** (`save_atomic`):
  - write to `.<name>.<random>.partial<ext>` in the chosen folder;
  - re-open it with an independent reader and check the signature and the row count;
  - flush it to disk and move it into place with `os.replace`;
  - check that the moved file has the verified size and SHA-256.
  A failure leaves the destination as it was and no partial file.
- **The checks:**
  - xlsx: `PK` signature, sheet names, header, and **every data cell** compared with the value written (openpyxl, read-only); cells the format cannot hold exactly must hold their planned replacement and are counted (`changed_cells`), any other difference fails the save;
  - csv: byte-order mark as chosen, UTF-8, header and record count with the csv module;
  - sav: `$FL2` signature, the variables (pyreadstat, metadata only), the rows of one column;
  - zip: CRC of every member, the SHA-256 of every file listed in the manifest, the data rows inside.
- A save the system refuses is explained in words (`workspace_files.explain`), as for every other export.

### 5.4 Participant data
- Before any row-level export, the card warns about columns that may identify participants (`data_export.sensitive_columns`):
  - names, e-mail, phone, address, birth date, personal code or IP, by column name in EN/LV/RU or by what most values look like (e-mail addresses, the Latvian *personas kods* shape, IPv4, phone numbers that are not dates);
  - participant codes (level *identifier*, confirmed or suggested);
  - free-text answers.
  It is a heuristic warning, never a guarantee either way. On the fixture it names `participant_code`.
- **Nothing is ever uploaded.** Exports write only to the folder chosen in the Save dialog. The manifest records `"uploaded": false`.

## 6. Dependency

- `requirements.in`: `pyreadstat>=1.3,<2`.
- `requirements.txt` was regenerated with the command in its own header:

```
uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements.txt
```

- **The diff** (commit `4bd86e5`):
  - the new entry `pyreadstat==1.3.7`, with the 26 hashes of all its published files;
  - one `#   pyreadstat` "via" line under narwhals and one under numpy.
  It now pins **50** packages instead of 49. No other pin or hash changed: compared pin by pin, 0 changed, 0 removed.
- **Dependencies:** pyreadstat 1.3.7 needs narwhals (2.28.0) and numpy (2.5.4), both already pinned.
- **Dev lock:** `requirements-dev.txt` regenerates byte-identical with its own command. The GUI driver installs both locks (`.github/actions/pinned-windows-toolchain`), so it has pyreadstat.
- **Windows:** the lock holds the hash of `pyreadstat-1.3.7-cp312-cp312-win_amd64.whl`, `7b65bd28c402376c5bafa44c691acf726904611621e09404bbf4827de78b4609`. It was checked against PyPI's metadata and against the downloaded wheel, and `tests/test_stage37_dependency.py` checks it.
- **Licences:**
  - pyreadstat is Apache-2.0 (its `License` metadata);
  - the ReadStat C library compiled into it is MIT (© Evan Miller). Both texts are in the wheel's `dist-info/licenses/LICENSE`, which the bundle keeps.
  - `tools/build_sbom.py` lists pyreadstat (`Apache-2.0`) and ReadStat as a component inside it (`MIT`, `BUNDLED_IN_WHEEL`), and both are in `licenses.md`. Neither is copyleft. `docs/STAGE368_BUILD_LOCK.md` §2.1 and §5 have the note.
- **Bundle size**, measured from the locked Windows wheel with the build's own cleanup globs (`tools/prune_packages.py`):
  - **+2.48 MiB installed** (12 files, mostly the two compiled modules of 1.2 MiB each);
  - **+1.62 MiB** as the sum of per-file deflate sizes, which approximates the growth of the installer and the portable ZIP;
  - the cleanup removes the 2.85 MiB of `.c`, `.pyx` and `.pxd` sources.
  - Not measured in a Windows build.

## 7. Performance

Linux container, Python 3.12.3, one table of 100,000 rows × 30 columns (3 million cells: 28 numeric, two text), write plus verification:

| Format | Time | File |
|---|---:|---:|
| `.xlsx` (Data only) | 48.5 s | 13.4 MiB |
| `.csv` | 5.4 s | 13.1 MiB |
| `.sav` | 1.5 s | 22.9 MiB |

The `.xlsx` time is openpyxl's own XML serialisation (≈ 100,000 cells/s) and the full re-read with openpyxl in read-only mode. Float columns skip the per-cell conversion. Progress is reported every 2,000 rows. (Measured before the review fixes; the check now also compares every cell it re-reads, not measured again.) The card computes the .xlsx and .sav previews once per version of the data, not on every render (review integration F2).

## 8. Windows journey `export-data`

`tools/windows_gui_e2e.py` gains the journey **`export-data`**. It is appended after the 18 existing journeys in `JOURNEYS`, whose order is unchanged (`tests/test_stage37_export_journey.py`). `tests/test_stage368_review_journeys.py` now expects 19 journeys.

The journey:
1. creates project *Fictional export study*;
2. generates the 180-case fixture with the stdlib generator and opens it in the Windows Open dialog;
3. on the Data page, finds the Export card, then for `.xlsx`, `.sav` and `.csv`:
   - chooses the format in the dropdown *Format*;
   - for `.sav`, waits for the text about what `.sav` cannot hold;
   - presses *Export .xlsx…* / *.sav…* / *.csv…*;
   - types the target in the **native Save dialog**;
   - waits for *Saved and checked* and the file name;
4. checks every file on disk with the driver's own independent readers (`check_export`):
   - openpyxl: no formula, sheets Data and Codebook, every cell;
   - pyreadstat: `$FL2`, names, every cell;
   - pandas: byte-order mark, every cell, and the codebook vouching for the CSV by SHA-256.
   Each cell is compared with the fixture as the driver reads it with the csv module;
5. checks that `preferences.json` remembers `csv`.

No disabled state is asserted, because UI Automation reports every button as enabled.

**Proof here:** `ExportDataJourneyTests.test_the_journey_flow_and_its_checks` walks the same flow in the harness with the journey's own texts, options and `check_export`. It also checks that the format is remembered after a restart. `test_the_journey_check_finds_a_changed_cell` shows that `check_export` fails on one changed cell.

**Not done:** a run on Windows. The journey runs in `windows-gui-e2e.yml`; its path filter now also covers `data_export.py`, `export_bundle.py`, `csv_safety.py`, `data_loader.py`, `app_preferences.py`, `import_workflow.py` (review integration F4) and the stage 37 generator.

The order tests are merge-tolerant (review integration F1): the eighteen first, `export-data` among the journeys after them, at least 19 (other Stage 37 branches append theirs there too).

**PR #78, journey `report-composition`, "the Interpretation section did not open"** (run 43498631988; the same failure on PR #77). Root cause, in the driver: `open_interpretation` found the section's header, then searched for the note field, which scrolls the page down, and then clicked the header element it had found before. The Export card makes the Results page about 240 px longer, enough for that search to scroll the header out of view (screenshot `235-…`: *Full report* at the top, the header above it), so the click landed above the content and the section never opened. A person is not affected: the header is on the page, nothing covers it, and the harness walk opens the section on the same page. The driver now looks up the header again, scrolled into view, right before each press (`tools/windows_gui_e2e.py`). `OpenInterpretationTests` reproduces it on a model of the scrolling page: the old driver fails on the longer page and passes on the shorter one; the new one passes on both and never closes an open section.

## 9. Test evidence

New test files:

| File | Tests | What they prove |
|---|---:|---|
| `tests/test_stage37_csv_guard.py` | 7 | D8: the rule, reversibility (4,000 random strings), both older exports protected, numbers unchanged, read back exactly only when the codebook or log vouches, an edited file keeps its apostrophes |
| `tests/test_stage37_dependency.py` | 4 | range and pin, the Windows wheel hash, 50 pins, narwhals and numpy unchanged; in the Windows runtime; SBOM Apache-2.0 + ReadStat MIT; the cleanup keeps the licence and the compiled modules |
| `tests/test_stage37_export.py` | 26 | round trips (below), SPSS names, preview, metadata storage and restart, codebook, results workbook, bundle, **R syntax**, engine seeds, atomic save, participant check, preferences |
| `tests/test_stage37_export_ui.py` | 10 | the card on the Data, Results and Reports pages; one click; `.sav` preview; CSV layout and byte-order mark remembered; a failed save; `.sav` opened with labels and the user-missing option; LV/RU; the bundle with the Word report; data export without a report |
| `tests/test_stage37_export_journey.py` | 3 | journey order; the `export-data` walk; its check catches a changed cell |
| `tests/test_stage37_export_fidelity.py` | 12 | review fixes (§12) with readers written for the tests: `.xlsx` with zipfile + ElementTree (`tests/xlsx_zip.py`), `.sav` with a struct-based reader of the dictionary and data (`tests/sav_struct.py`): every cell of the fixture exact, adversarial values exact or changed as planned, dates before 1900, the cell-by-cell check, short names, string widths, windows-1251 names |

After the review fixes (§12) the files hold: `test_stage37_csv_guard.py` 14, `test_stage37_export.py` 30, `test_stage37_export_ui.py` 13, `test_stage37_export_journey.py` 6 (with `OpenInterpretationTests`), `test_stage37_export_fidelity.py` 12.

**Round trips** (fixture: 180 cases × 98 variables, plus adversarial columns):
- cells beginning with `= + - @`, a tab or an apostrophe;
- a 75-character Latvian and a 73-character Russian variable name (85 and 131 UTF-8 bytes);
- date-times and dates with gaps;
- `000`…`179` identifiers;
- a rating with labels for its missing codes −9 and −8, which are declared user-missing;
- an unlabelled numeric variable;
- empty texts beside missing ones;
- doubles that need 17 digits.

| Round trip | Independent reader | Result |
|---|---|---|
| app → `.xlsx` | openpyxl (cell by cell, types), pandas.read_excel | values exact (17-digit doubles within 1e-15); dates as datetimes; `000` stays text; formula texts are text cells and the XML holds no `<f>`; missing has no cell, an empty text is a text cell; Codebook: levels, value labels, missing codes, counts (`rating`: 60 user-missing, 30 missing); Provenance: dataset SHA-256 |
| app → `.csv`, comma and semicolon | pandas.read_csv | every number exact, decimal comma included; texts equal after `restore`; only `""` vs missing merges, as documented |
| app → `.csv` → app | data_loader | every protected text restored, numbers exact, `1,234` read as 1.234 in the semicolon layout, leading zeros kept; labels, value labels and missing codes come back as metadata, and the level as a suggestion only |
| app → `.sav` | pyreadstat.read_sav | values exact; SPSS names; measures equal to the confirmed levels; missing (−9, −8) declared; value labels; labels cut at 256 bytes on a character boundary; `code_lz` is a string with its zeros; missing Russian text is `""` declared missing, NaN when read normally; UTF-8 |
| app → `.sav` → app | data_loader | the original names come back, the long LV/RU ones included; metadata equal; user-missing values missing by default; with `user_missing="codes"` the `rating` series is equal |
| external `.sav` → app → `.sav` | pyreadstat.read_sav | values equal (codes kept), labels, value labels, missing values (discrete, range plus code, string) and measures equal |
| the bundle | zipfile + manifest | every file's SHA-256, 180 rows, all members, seeds, syntax only where verified |
| the bundle's R syntax | Rscript 4.3.3 | **29/29 check values** within 1e-9 of the engine |

**Full suite** (Linux, Python 3.12.3, a venv from both hashed locks, R 4.3.3 present, so the R syntax test ran):
- before the change (`2f9af71` with the lock change): 1,326 tests, OK, 10 skipped (999 s);
- after it (`b210777`): **1,376 tests, OK, 10 skipped** (1,043 s). The 50 new tests are the five files above.
- after the review fixes of §12 (`13dfab9`): **1,405 tests, OK, 10 skipped** (937 s), R 4.3.3 present.

Run with:

```
SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 python -m unittest discover -s tests
```

## 10. Limitations

- **xlsx:** no infinities, integers above 2⁵³, dates before 1900-03-01, time zones or durations as such (text instead); control characters XML cannot hold become U+FFFD; texts over 32,767 characters are cut; one worksheet (≤ 1,048,575 rows). Each such change is listed before saving and in the outcome, with CSV as the exact alternative. A 16-digit identifier is still written as a number (review X6, not changed). Result sheets: the overview names the sheet the workbook really has (review X4).
- **CSV:** types are not carried (the codebook says them). A reader that ignores quotes merges `""` with missing. The formula protection is visible in other programs as a leading apostrophe; only this program, with the codebook, removes it.
- **.sav:**
  - missing texts and empty texts become one declared-missing blank;
  - at most three missing codes or a range and a code;
  - categories become codes with labels; on import they come back as codes with value labels, not as a pandas categorical;
  - time zones are converted to UTC;
  - no audit trail, history or provenance;
  - default import makes user-missing values missing; keeping the codes is an explicit option;
  - missing codes and value-label codes longer than a string variable's width are not written (listed);
  - texts over 32,767 bytes are written as very long strings that PSPP splits (review SAV-5, not changed); files are not compressed (SAV-10, not changed).
- **Metadata:** there is no editor in this increment. Metadata comes from `.sav` files, exported codebooks and questionnaires. Metadata is not imported from an `.xlsx` Codebook sheet.
- **Syntax:** R only, for four method families. No SPSS syntax.
- **Participant warning:** a heuristic, so false positives and misses are possible.
- **Performance:** `.xlsx` is about 60,000 cells/s including the check (§7).
- **Windows:**
  - the journey has not run on Windows;
  - no measurement of the installed size;
  - no screenshot evidence of the card on Windows.
- **Locale:** LV and RU texts are drafts.

## 11. Done / not done

| Item | Status | Proved by |
|---|---|---|
| Data → .xlsx (openpyxl), .sav (pyreadstat), .csv (UTF-8, optional byte-order mark) | done | §9 round trips |
| Codebook: name, label, level, value labels, valid and missing codes, scales, reverse items, history | done | `CodebookTests`, `XlsxRoundTripTests.test_codebook_scales_and_provenance_sheets` |
| Results: editable .xlsx, per analysis, with provenance | done | `ResultsAndBundleTests.test_results_workbook_sheets_engine_values_and_provenance` |
| Bundle: manifest (dataset SHA-256, versions, methods, options, seeds), codebook, data, results, DOCX, figures | done | `test_the_bundle_manifest_files_and_checksums`, `test_the_bundle_from_the_reports_page_holds_the_word_report` |
| R syntax only where verified | done (R, 4 method families, 29 values) | `test_the_r_syntax_reproduces_the_engine` (needs Rscript) |
| SPSS syntax | not done | no SPSS or PSPP verification available |
| xlsx sheets Data, Codebook, Scales, Results, Provenance, selectable | done | `XlsxRoundTripTests`, `DataExportTests` |
| Numbers, dates, leading zeros, missing vs blank, explicit text cells | done | `test_values_types_and_missing_survive_openpyxl`, `test_no_cell_is_ever_a_formula` |
| CSV formula protection: documented, reversible, numbers unchanged | done | `test_formula_injection_is_neutralised_and_numbers_are_not`, `test_stage37_csv_guard` |
| Streaming with progress | done | `test_streaming_reports_progress_and_refuses_what_excel_cannot_hold`, §7 |
| .sav: levels, labels, value labels, user-missing within limits; SPSS names with a reversible rename table shown as a preview; Unicode and widths; what .sav cannot carry shown | done | `SavRoundTripTests`, `test_the_sav_preview_lists_every_renamed_or_cut_field_before_saving` |
| Review: identifiers as strings; at most 3 codes or 1 range (+1 code); every renamed or cut field previewed | done | `test_the_preview_lists_every_renamed_cut_or_converted_field` |
| Review D8: older CSV exports protected (red test first, own commit) | done | `tests/test_stage37_csv_guard.py`, commit `2ef9110` |
| Review M2: labels, value labels, missing codes in the model and stored in format 6 without a new column | done | `MetadataStorageTests` (both) |
| Review M2: editor | not done | import from .sav and from the exported codebook instead |
| Review H2: semicolon separator and byte-order mark, remembered | done | `test_semicolon_layout_…`, `test_csv_separator_and_byte_order_mark_are_offered_and_remembered`, `LanguageTests` |
| .sav import with labels and missing codes; round trips both ways | done | `test_the_program_restores_names_and_metadata_from_its_own_sav`, `test_an_external_sav_comes_in_and_goes_out_with_its_metadata`, `test_an_spss_file_opens_with_its_labels_and_its_missing_option` |
| Dependency: range, hashed lock, cp312 win_amd64 hash, licences, SBOM, size | done (size from the wheel, not from a build) | `tests/test_stage37_dependency.py`, §6 |
| One Export action in Data, Results, Reports; remembered format; folded options; exact default, or every change listed with CSV offered; no report needed | done | `test_stage37_export_ui` |
| Atomic save, success location, verification after saving | done | `AtomicSaveTests`, every round trip (`verified`) |
| Participant warning; nothing uploaded | done | `SensitivityTests`, `test_participant_codes_are_flagged_and_nothing_is_uploaded` |
| EN/LV/RU (LV/RU drafts) | done (drafts) | `LanguageTests`, `test_locale_audit`, `test_workspace_foundations` |
| Windows journey `export-data`, walk test | written, walked in the harness | `tests/test_stage37_export_journey.py` |
| Windows journey run on installed Windows | not done | CI `windows-gui-e2e.yml` |
| `.por`, `.dta` | not done | no separately validated writer (spec: optional) |

## 12. Review of the branch: findings fixed and deferred

The verification of `619143d` (lenses injection, sav, xlsx, integrity, integration; only confirmed findings). Each fix has a test that failed on the code before it and passes after it.

| Finding | Severity | Status | Fix | Test |
|---|---|---|---|---|
| injection F1-separator-split | major | fixed | CSV rule v2: an apostrophe at every place a cell can start (§5.1) | `SeparatorSplitTests`, `RuleTests.test_a_formula_after_a_separator_space_or_quote_is_protected_too` |
| injection F2 | major | fixed | `survey_storage.export_survey_responses` for both interfaces | `ClassicSurveyExportTests` |
| injection F3 (LF, full-width) | minor | fixed | part of rule v2 | `RuleTests` |
| injection F5 / integrity F5 | minor | fixed | `data/<name>_codebook.json` in the bundle | `test_the_bundle_manifest_files_and_checksums` |
| injection F6 | minor | fixed | `names(d) <- unprotect(names(d))` | `test_r_syntax_reproduces_text_coded_groups_and_protected_names` |
| injection F7 | minor | fixed | infinities as protected text in CSV | `test_an_infinity_is_never_a_bare_cell_that_begins_with_minus` |
| injection F8 / xlsx X2 / integrity F1 | major | fixed | `plan_xlsx`, the card's list before saving, the outcome, the manifest, the cell-by-cell check (§2.1) | `test_cut_or_replaced_cells_are_named_before_and_after_saving`, `test_the_bundle_names_every_value_its_xlsx_copy_changes`, `test_a_cell_the_writer_changes_unplanned_fails_the_check`, `test_adversarial_values_are_exact_or_changed_as_planned` |
| xlsx X1 | major | fixed | dates before 1900-03-01 as ISO text, listed | `test_dates_before_1900_survive_or_become_text`, `test_adversarial_values_are_exact_or_changed_as_planned` |
| xlsx X3 | minor | fixed | shortest exact number text while writing | `test_every_cell_of_the_fixture_is_exact` |
| xlsx X4 | minor | fixed | the overview names the cleaned sheet title | `test_results_workbook_sheets_engine_values_and_provenance` |
| xlsx X5 | minor | fixed | U+FFFE, U+FFFF, lone surrogates replaced; control characters left out of sheet titles | `test_adversarial_values_are_exact_or_changed_as_planned` (C0); by code reading for the rest |
| sav SAV-1 | major | fixed | string missing codes wider than the variable not declared, listed | `test_string_missing_codes_fit_the_written_width` |
| sav SAV-2 | major | fixed | `unique_short_names` after writing | `test_short_names_are_unique_ignoring_case`, `test_random_name_sets_give_unique_short_names` |
| sav SAV-3 | major | fixed | reader path without ReadStat's long-names parsing | `test_cp1251_name_with_ya_imports` |
| sav SAV-6 | minor | fixed | value labels with codes wider than the variable left out, listed | `test_a_label_code_longer_than_the_variable_is_left_out_and_listed` |
| sav SAV-13 | minor | fixed in the tests | the struct-based `.sav` reader of the tests (`tests/sav_struct.py`) compares dictionary and data; the program's own check is still pyreadstat | `SavIndependentReaderTests` |
| integrity F2 | major | fixed | R reads every column as text, numbers converted, group codes as written (§2.6) | `test_r_syntax_reproduces_text_coded_groups_and_protected_names`, `test_the_r_unprotect_is_the_program_s_restore` |
| integrity F3 | major | fixed | metadata bound to the dataset (§3.1) | `test_a_new_file_does_not_inherit_another_files_metadata` |
| integrity F9 / integration F3 | minor | fixed | the Data card's outcome is cleared on a project switch | `test_another_project_does_not_show_the_previous_export` |
| integration F1 | major | fixed | merge-tolerant order tests | `JourneyOrderTests` (both files) |
| integration F2 | minor | fixed | previews cached per data version | by code reading |
| integration F4 | minor | fixed | path filter | by reading the workflow |
| CI, PR #78 `report-composition` | — | fixed in the driver | §8 | `OpenInterpretationTests` |
| injection F4 (a forged codebook is not authentication) | minor | deferred | the SHA-256 binding says *exported with this file*, not *by whom*; stripping the apostrophes gives only texts any CSV can carry, and every export protects them again. A signed codebook needs a key the program does not have | — |
| sav SAV-4 (encoding option ignored for .sav) | minor | deferred | outside the export path; the declared code page is used | — |
| sav SAV-5, SAV-10 (texts over 32,767 bytes, no compression) | minor | deferred | not reached by the fixture; listed in §10 | — |
| sav SAV-7 (durations as text without a preview line) | minor | deferred | rare in the data the program imports | — |
| sav SAV-8, SAV-9, SAV-11 | minor | deferred | case-only clashes on re-import, ±∞ ranges in the JSON codebook, user-missing dates: import-side behaviour, not in this fix | — |
| xlsx X6 (16-digit identifiers as numbers), X7 (bundle without the .xlsx for over 1,048,575 rows) | minor | deferred | change the .xlsx data model for identifiers or the bundle's member list; not in this fix | — |
| integrity F4, F6, F7, F8, F10, F11 | minor | deferred | two-step CSV save, temporary files of the bundle in the system temp folder, the participant heuristic, omega seeds, the importer's NA texts, trailing spaces in .sav texts: each needs its own change and test | — |
| integration F5 (SBOM count in STAGE368_BUILD_LOCK.md) | minor | deferred | documentation of the build lock, not export fidelity | — |

