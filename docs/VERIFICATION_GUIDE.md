# How to do every human check

This guide walks you through every check in `docs/VERIFICATION.md` that only a person can do. The computer has already built and tested everything it can. What is left needs your eyes, your judgment, and your signature.

Each check below tells you:

- what the check is, in plain words,
- why it matters,
- exactly what to click or type,
- what "good" looks like and what "bad" looks like,
- exactly what to write into `docs/VERIFICATION.md`.

Read Part 0 before you write anything.

---

## Part 0. Read this first: what is already filled in

An AI agent ran every check it could on 2026-11-18 and wrote the results into `docs/VERIFICATION.md`. Each of those entries says "(agent)". For each one, redo the check with this guide, then delete "(agent)" if you agree, or correct the entry if you do not.

What only you can do: the drill rehearsals, the Safari line if you have an Apple device, the close-up look at the drone, and re-voicing the reasons in `docs/DECISIONS.md` so they sound like you. An agent wrote those reasons from each record's own text.

The document tests now check the format of your entries, not that they are empty. A filled `Date:` must hold a real date like `2026-11-20`. Log lines do not count toward the 400-word limit of `docs/VERIFICATION.md`.

Two more document rules that stay true even after the tests are updated:

- Do not write any drive path (like `C:\...`), any `/Users/...` path, your Windows username, or anything that looks like an email address into `docs/VERIFICATION.md`. The test `test_doc_no_personal_paths` rejects them.
- Do not use the long dash character. Use a comma, a colon, or a new sentence.

---

## Part 1. How to launch the demo

You need the demo running for most checks. Here is how to start it, use it, and stop it. Every command below was run on this machine on 2026-11-18 and worked, unless the step says otherwise.

### 1.1 Open a terminal in the repository folder

The "repository folder" (also called the "repo root") is the folder that holds `README.md`, `aois.toml`, and `SPEC.md`. Every command in this guide must be typed there.

**PowerShell (the normal Windows terminal):**

1. Press the Windows key, type `PowerShell`, press Enter.
2. Type this and press Enter:

```powershell
cd ~\ClaudeProjects\terrain-tile-demo
```

3. Check you are in the right place:

```powershell
dir README.md, aois.toml
```

Good: both files are listed. Bad: "Cannot find path". Then you are in the wrong folder.

**Git Bash (if you prefer):** right-click inside the repo folder in File Explorer, choose "Open Git Bash here". Or type `cd ~/ClaudeProjects/terrain-tile-demo`.

Both terminals work for every `uv run ...` command. Where a command differs between them, this guide shows both.

### 1.2 Install the tools (first time only)

You only need this once, or after the lock files change.

```powershell
uv sync --no-build
npm ci
```

- `uv sync --no-build` installs the Python packages.
- `npm ci` installs the JavaScript packages.

Time: not measured in this session, because both were already installed. Expect under a few minutes on a normal connection. Good: both end with no red error text.

### 1.3 Check the toolchain

```powershell
uv run tilepipe preflight
```

Time: a few seconds. Good: seven lines, `PF-01` to `PF-07`, every one says `PASS`. On this machine it showed Blender 5.2.0 LTS, Node v24.16.0, Python 3.12.13, and ffmpeg.

Bad: any line says `FAIL`. Stop and ask an agent.

### 1.4 Build everything

There are two ways. Use the first one for most checks.

**Fast build without Blender (verified, about 7 seconds):**

```powershell
uv run tilepipe all --no-blender
```

This runs four steps in order: build the terrain, copy the already-exported entity files, run all validation rules, and assemble the website into the `site/` folder. It does not open Blender.

**Full build with Blender (about 40 seconds, measured by an earlier audit, not re-run today):**

```powershell
uv run tilepipe all
```

This also runs Blender in the background to check and re-export the three entities. Use this one when the video needs the real "one command" timing.

What good looks like, near the end of the output:

```text
validate: 275 PASS, 2 WARN, 13 FAIL (13 expected by fixtures), 5 SKIP
site: wrote site/
```

The 13 FAIL lines are on purpose. They come from test files that are built to break a rule (called fixtures, see the glossary). The words "13 expected by fixtures" mean they all broke the rule they were meant to break. The 2 WARN lines are TER-09, which is allowed.

Two more lines are normal and not errors:

```text
site: assets/room.jpg is absent and is not created here
site: assets/fallback.jpg is absent and is not created here
```

These are pictures you provide (see Part 5).

To check the exit code (0 means success):

- PowerShell: `$LASTEXITCODE`
- Git Bash: `echo $?`

Good: `0`. Bad: any other number.

### 1.5 Start the viewer

The viewer is a small website that runs on your own computer. Nobody else can see it.

```powershell
uv run tilepipe serve
```

Good: it prints

```text
Serving site/ at http://127.0.0.1:8000/ (Ctrl+C to stop)
```

and then it waits. It does not give you the prompt back. That is correct: the terminal is now busy being a web server. Leave that window open.

Open your browser and go to:

```text
http://127.0.0.1:8000/
```

Time: the server starts in about a second. The page should show the terrain within 10 seconds.

This was verified today: the server answered with code 200 for the main page, for `data/anza_borrego_01/tile.json`, and for `report/index.html`, and it sent `.glb` files as `model/gltf-binary`.

Bad: "site/ is empty; run `uv run tilepipe site` first". Then run step 1.4 again. Also bad: an error about the address being in use. Then an old server is still running. See step 1.6.

### 1.6 Stop the viewer

1. Click the terminal window that says "Serving site/".
2. Press `Ctrl` and `C` together.
3. The prompt comes back.

Check that nothing is still listening on port 8000:

```powershell
netstat -ano | findstr :8000
```

Good: no line contains `LISTENING`. Lines with `TIME_WAIT` are leftovers that vanish on their own within a minute or two. They are fine.

Bad: a line like `TCP 127.0.0.1:8000 ... LISTENING 44520`. The last number is the process ID. Stop it:

```powershell
taskkill /PID 44520 /F
```

(In Git Bash, type `taskkill //PID 44520 //F`, with double slashes.)

This was verified today: after stopping, `netstat` showed no `LISTENING` line on port 8000, and a request to the address got no answer.

### 1.7 Useful viewer addresses

Add these to the end of the address. You can combine them with `&`.

| Address | What it does |
| --- | --- |
| `http://127.0.0.1:8000/` | Normal start. The tour plays once. |
| `http://127.0.0.1:8000/?tour=0` | Starts without the tour. Best for screenshots. |
| `http://127.0.0.1:8000/?profile=mobile_ar` | Starts on the Mobile AR profile. |
| `http://127.0.0.1:8000/?probe=1` | Writes one test reading to the browser console (for the position check). |
| `http://127.0.0.1:8000/?bench=1` | Runs the speed test and offers `bench.json` for download. |
| `http://127.0.0.1:8000/report/` | The validation report. Also linked from the "Full report" link in the Budget panel. |

### 1.8 Viewer controls

Mouse:

- Left button and drag: turn the view around the tile.
- Scroll wheel: move closer or further. The closest you can get is 0.3 m and the furthest is 3 m.
- Right button and drag: slide the view sideways.

Keys:

| Key | Does |
| --- | --- |
| `1` | Workstation profile |
| `2` | Mobile AR profile |
| `L` | Switch look between Opaque and Additive |
| `E` | Change height exaggeration |
| `C` | Contour lines on or off |
| `G` | Grid on or off |
| `W` | Wireframe on or off |
| `T` | Play or stop the tour |
| `R` | Reset the camera |
| `H` | Hide or show all panels |

Panels on screen: a title panel with an "About" button, a profile switch, a "Budget" panel, a "Cursor" panel (shows the position under your mouse pointer), and a "View" panel (look, exaggeration, contours, grid, debug view None / Wireframe / LOD tint, and a "Play tour" button).

### 1.9 Open Blender with the repo's extension

You need this for the panel check, the token review, and drill D2.

**Step A. Build the extension file (verified, about 1 second).** In PowerShell, from the repo root:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --factory-startup --command extension build --source-dir blender\tilepipe_tools --output-dir $env:TEMP
```

Good: it prints `building: tilepipe_tools-1.0.0.zip` and `complete`. The zip lands in your temp folder, outside the repo, so git does not see it. You can open the folder with `explorer $env:TEMP`.

**Step B. Install it.**

1. Start Blender 5.2 normally from the Start menu.
2. Click Edit, then Preferences.
3. Click "Get Extensions" on the left.
4. Click the small down-arrow menu at the top right of that page, and choose "Install from Disk...".
5. Pick `tilepipe_tools-1.0.0.zip` from your temp folder.
6. It now shows as "Tile Pipeline Tools". Make sure its checkbox is on.

**Step C. Tell it where the repo is.**

1. In the same Preferences window, expand "Tile Pipeline Tools".
2. In "Repository root", choose your repo folder (the one with `README.md`).
3. Close Preferences. Blender saves preferences automatically by default.

**Step D. Open an entity and find the panel.**

1. File, Open, then choose `assets\entities\ent_vehicle_wheeled_a\ent_vehicle_wheeled_a.blend` inside the repo.
2. Hover the mouse over the 3D view and press `N`. A sidebar opens on the right.
3. Click the tab named "Tile Pipeline".
4. In the Outliner (top right list), click the collection named `ent_vehicle_wheeled_a` so it is active.
5. Click "Validate Asset".

Good: every row in the result list passes. Bad: the panel says "Set repo_root in the add-on preferences." Go back to Step C.

**Important:** Do not save the `.blend` file (Ctrl+S) after you change things for a test. It is a tracked file. If Blender asks whether to save when you close, say "Don't Save".

### 1.10 Run the tests

```powershell
uv run pytest -q
```

Time: about 2.5 to 3 minutes. Good today, before you fill anything in: `260 passed`. After you fill in the logs, expect the three failures from Part 0 until the tests are updated.

---

## Part 2. Glossary

**AOI.** "Area of interest." The patch of Earth the demo shows. Here it is `anza_borrego_01`, a 10.24 km square around Borrego Palm Canyon in California. All AOI values live in `aois.toml`.

**Art lock.** The moment you freeze the look files so nobody changes the colors any more. You prove they are frozen by writing down their hashes.

**Bench, bench mode, `bench.json`.** A speed and count test the viewer runs on itself. It turns the view for 600 frames per profile and writes the results to a small file called `bench.json`.

**Budget.** A maximum allowed amount, like "at most 112,500 terrain triangles" or "at most 20 draw calls". Each profile file has a `[budget]` list.

**Chunk.** The tile is cut into a 4 by 4 grid of 16 pieces. Each piece is a chunk, named like `c2_0`.

**Contour lines.** Lines that join points of the same height, like on a hiking map. "Index" contours are the thicker, every-fifth ones.

**DCC.** "Digital content creation" tool. A program artists use to make 3D models. Here, that is Blender.

**DEM.** "Digital elevation model." A grid of height values for the ground. The source is a USGS DEM.

**Determinism.** Running the build twice gives byte-for-byte the same files. Rule DET-01 checks this.

**Draw call.** One "please draw this" command from the program to the graphics card. Fewer is better on weak hardware.

**Drill.** A practice exercise you rehearse so you can do it live in front of people, without an agent. There are four, D1 to D4.

**Entity.** One of the three small models standing on the terrain: a truck (`ent_vehicle_wheeled_a`), a radio mast (`ent_mast_comms_a`), and a small four-rotor drone (`ent_uas_quad_a`). They are simple placeholder shapes made by a script.

**Exaggeration.** Stretching heights upward so hills look taller than in real life. Only applied when drawing. The stored data stays true scale.

**Fixture.** A test file built on purpose to break exactly one rule, to prove the rule catches it. Fixtures failing is good.

**FAIL / WARN / PASS / SKIP.** Results of a rule. PASS: fine. WARN: worth a look but allowed. FAIL: not allowed (unless it is an expected fixture failure). SKIP: not run, with a reason given.

**Gate G1, G4, G5, G6, G7.** Checkpoints in the build plan. A gate is a list of things that must be true before moving on. G1 is "the data is right". G4 is "the viewer works". G5 is "the entities work". G6 is "everything works together". G7 is "publish".

**GDAL.** A standard library for reading map data files. Its version is recorded in `build_info.json`.

**GLB / glTF.** A common file format for 3D models. glTF is the format; GLB is the single-file binary version of it.

**Hash (SHA-256).** A 64-character fingerprint of a file. If even one letter in the file changes, the fingerprint changes completely. You record it to prove a file has not changed.

**HAE.** "Height above ellipsoid." Height measured from a smooth math shape of the Earth. This project does not use it.

**Hero screenshot.** One of six specific pictures of the viewer, H1 to H6, saved for the README and the docs.

**HUD.** "Heads-up display." The panels drawn on top of the 3D view.

**LOD.** "Level of detail." The same thing stored with more or fewer triangles. Far away or on weak hardware, use fewer. LOD 0 is the most detailed.

**LOD tint.** A debug view that colors each chunk by which LOD it uses.

**MGRS.** "Military Grid Reference System." A way of writing a map position as one string, like `11SNS5307082470`. Here it is used only as a standard position format.

**NAVD88.** The official US standard for "height above sea level". Heights in this project are NAVD88 heights in meters.

**Pixel error.** How far, in screen pixels, a simplified terrain edge can be from the true shape.

**Profile.** A description of one class of hardware, with its budgets. There are two: `workstation` (a desktop PC with a good graphics card) and `mobile_ar` (a headset that runs on its own with a see-through screen). They live in `profiles/`.

**Rule ID (like ENT-03, SCN-04, TER-09).** Each check the validator runs has a short name. The letters say the family (ENT: entity source, ENTD: entity export, SCN: scene, TER: terrain, LOOK: look files, and so on).

**Threshold.** The number a rule compares against, like "at most 4 pixels".

**Token.** Here, an entity, because it works like a game piece on a tabletop.

**USGS.** United States Geological Survey. The government agency that published the free elevation data.

**UTM.** "Universal Transverse Mercator." A map grid that measures positions in meters east (easting) and north (northing) inside numbered zones. This tile is in zone 11.

**Validator.** The program that runs all the rules and writes the report.

**WGS84.** The worldwide standard for latitude and longitude, used by GPS.

---

## Part 3. How to write into `docs/VERIFICATION.md`

1. Open `docs/VERIFICATION.md` in any text editor (Notepad works).
2. Find the line for the check. It looks like `- [HUMAN] Date:`.
3. Type your answer after the colon, on the same line, with one space first. Example: `- [HUMAN] Date: 2026-11-19`.
4. Keep the `- [HUMAN]` at the start. Do not delete lines.
5. Write dates as year-month-day, like `2026-11-19`.
6. Keep answers short. The file has a 400-word limit (see Part 0).
7. Save the file.

---

## Part 4. One section per log entry

### 4.1 AOI sign-off (gate G1)

**What it is.** You look at two pictures of the area and confirm it is the place you meant, and that it looks good.

**Why it matters.** If the computer picked the wrong patch of Earth, everything after it is wrong. Only a person can say "yes, that is Borrego Palm Canyon".

**Steps.**

1. Make sure you have built once (Part 1.4).
2. Open these two pictures (double-click them in File Explorer):
   - `build\anza_borrego_01\preview_hillshade.png` (gray, looks like a lit clay model)
   - `build\anza_borrego_01\preview_hypso.png` (colored by height)
3. Compare them with an online map in terrain mode, centered near latitude 33.28, longitude -116.43. Top of the picture is north.

**Good.** You see steep mountains on one side and the flat desert floor of Borrego Valley on the other, and the shapes match the map. The pictures are sharp, have no holes or blank stripes, and are 1024 by 1024 pixels.

**Bad.** The place looks different from the map, or the pictures show flat nothing, stripes, holes, or a mirror image. Then write FAIL and stop. Ask an agent.

**What to write.**

```text
- [HUMAN] Date: 2026-11-19
- [HUMAN] Result: PASS, Borrego Palm Canyon confirmed, previews read well
```

### 4.2 MGRS cross-check

**What it is.** The program wrote the tile center as an MGRS string. You check it against a different, independent tool.

**Why it matters.** If two separate tools agree, you can trust the position is right. This catches mistakes in the position math.

**Steps.**

1. Run the first build step on its own to see the numbers:

```powershell
uv run tilepipe build --to prep
```

2. Look for the line that starts `prep: tile center`. Today it said:

```text
prep: tile center lat 33.279970, lon -116.430092, UTM E 553070, N 3682470, MGRS 11SNS5307082470
```

   You can also read `mgrs_center` in `build\anza_borrego_01\geo.json`.

3. Use the latitude and longitude from that line, **not** the ones in `aois.toml`. The tile snaps to a grid, so its center is a few meters away from the number in `aois.toml`.
4. Put `33.279970, -116.430092` into an independent converter. Any well-known "latitude longitude to MGRS" converter on the web works. Google Earth Pro also works: Tools, Options, then under "Show Lat/Long" pick "Military Grid Reference System", then search the coordinates. Set the result to 1 m precision (5 plus 5 digits).

**How to compare.** Break the string into four parts. `11SNS5307082470` is:

| Part | Value | Meaning |
| --- | --- | --- |
| Grid zone | `11S` | Big zone |
| 100 km square | `NS` | Square inside the zone |
| Easting | `53070` | Meters east inside the square |
| Northing | `82470` | Meters north inside the square |

**Good.** Grid zone and square letters are exactly the same. Easting and northing each differ by 2 or less.

**Bad.** Any letter differs, or a number differs by more than 2. Do not change any number to make it match. The plan then removes MGRS from the viewer and keeps only UTM. Ask an agent.

**What to write.**

```text
- [HUMAN] Date: 2026-11-19
- [HUMAN] Tile-center MGRS `prep`: 11SNS5307082470
- [HUMAN] MGRS from independent converter: <the string it gave you>
- [HUMAN] Result: PASS, zone and square match, digits within 2 m
```

### 4.3 Browser matrix, plus the other viewer checks (gate G4)

**What it is.** You open the viewer in each browser you have, check it works, and write down the browser names and versions. The same gate also asks for a few more checks, listed below. The log has only one line for them, so put short notes there.

**Why it matters.** Web graphics behave differently in different browsers. People clicking your link will use any of them.

**Browsers to test.** Current Chrome, Edge, and Firefox on this PC. Safari only if you have an Apple device. Any browser you did not test is written as "not tested".

**Find the version.** Chrome: type `chrome://version` in the address bar. Edge: `edge://version`. Firefox: menu, Help, About Firefox.

**Steps for each browser.**

1. Start the viewer (Part 1.5).
2. Press `F12` to open the developer tools. Click the "Network" tab. Tick "Disable cache".
3. Press `Ctrl` + `F5` to reload, and count seconds.
   - Good: the terrain appears and you can turn it within 10 seconds.
4. Watch the tour. It runs four 5-second steps with captions at the bottom. Then reload and click once during the tour.
   - Good: the tour plays, and your click stops it.
5. Press `1`, then `2`. Press `L` to switch looks on each. Try every key in the table in Part 1.8, and every control in the View panel.
   - Good: both profiles and both looks draw, every key and control does something sensible.
6. In the Network tab, look at the "Domain" or address column of every request.
   - Good: every request goes to `127.0.0.1:8000`. Bad: any other address.
7. Only in one browser (Chrome is easiest), the position check:
   1. Open `http://127.0.0.1:8000/?probe=1`.
   2. Press `F12`, click "Console". Find the line starting with `PROBE`.
   3. Good: `easting` is `553070`, `northing` is `3682470`. (These come from E0 547950 plus 5120, and N_top 3687590 minus 5120.)
   4. Now hover the mouse near the middle of the tile. The Cursor panel should show UTM within 10 m of E 553070, N 3682470, and an MGRS string starting with `11SNS`.

**Bad, any browser.** A black page, a message saying the demo needs WebGL2, missing terrain, frozen controls, or requests to other websites. Write it down for that browser.

**What to write.** One line, short:

```text
- [HUMAN] Date: 2026-11-19
- [HUMAN] Browsers versions checked: Chrome 1xx PASS, Edge 1xx PASS, Firefox 1xx PASS, Safari not tested; probe exact; pacing 0.002
```

The "pacing" number comes from the bench capture below.

#### Feeder task: bench capture (feeds the browser line and gate G4)

1. Start the viewer. In Chrome, open `http://127.0.0.1:8000/?bench=1`.
2. Do not touch anything. It turns the view for each profile. Expect roughly half a minute.
3. When it finishes, it shows the results and a link "Download bench.json". Click it. The file goes to your Downloads folder.
4. Move it into the build folder. PowerShell:

```powershell
Move-Item $HOME\Downloads\bench.json build\anza_borrego_01\bench.json -Force
```

5. Run the rules again:

```powershell
uv run tilepipe validate
```

6. Open `http://127.0.0.1:8000/report/` and press `Ctrl` + `F`, search for `SCN-04` and `PERF-01`.

**Good.** SCN-04 says PASS for both profiles (the live counts equal the planned counts). PERF-01 shows a fraction near 0.002 or smaller. Write that fraction as the "pacing" number. An earlier audit measured 0.0017.

**Bad.** SCN-04 FAIL. Ask an agent.

Note: `build/` is not tracked by git, so this file stays local.

#### Feeder task: the six hero screenshots (`docs/img/`)

**What they are.** Six pictures at exactly 1920 by 1080 pixels.

| Name | What to show |
| --- | --- |
| H1 | Workstation profile, Opaque look, default view |
| H2 | Mobile AR profile, Additive look |
| H3 | Workstation with LOD tint and Wireframe on |
| H4 | Mobile AR with LOD tint |
| H5 | Close up on entities, camera about 0.4 m away |
| H6 | Seen from straight above, Grid on |

**How to take one at exactly 1920 by 1080 in Chrome.**

1. Open `http://127.0.0.1:8000/?tour=0`.
2. Press `F12`, then `Ctrl` + `Shift` + `M` (device toolbar).
3. At the top, pick "Responsive" and type `1920` and `1080`.
4. Set up the view (profile, look, debug view).
5. Click the three-dot menu of the device toolbar and pick "Capture screenshot".
6. Save it into a new folder `docs\img\` with a clear name, for example `h1_workstation_opaque.png`.

**Extra.** Convert H1 to JPEG and save it as `assets\fallback.jpg` (in the repo root `assets` folder; that is where the code looks). The spec also wants H1 as the README hero picture. You can convert with ffmpeg, which is installed:

```powershell
ffmpeg -i docs\img\h1_workstation_opaque.png -q:v 2 assets\fallback.jpg
```

Then run `uv run tilepipe site` so the site picks it up.

**Good.** Six sharp pictures, each 1920 by 1080, each showing what the table says.

These are new tracked files. Adding and committing them is your choice.

### 4.4 Entity front-direction check in viewer (gate G5)

**What it is.** Each entity has a front. You check that in the viewer each one faces the direction the scene file says.

**Why it matters.** If the export flipped the models, every truck would drive backwards. A rule cannot see that. You can.

**Which end is the front.** The models are built with the front toward minus Y in Blender.

- Truck: the front is the end with the cab (the taller, shorter box). The long flat box is the cargo bed at the back.
- Mast: it is almost the same from every side. The dish faces point front and back.
- Drone: almost the same from every side. The landing skids run front to back.

**Steps.**

1. Open `scene\anza_borrego_01_scene.json` in Notepad. Each entry has `entity` and `heading_deg`. The heading is clockwise from north: 0 north, 90 east, 180 south, 270 west. The first truck has heading 66, so its cab should point east-north-east.
2. Open the viewer with `?tour=0`. Zoom in on a truck.
3. To know where north is: move your mouse pointer a little. In the Cursor panel, northing grows toward north and easting grows toward east.
4. Check that the cab points along the heading. Check two or three trucks.
5. For the mast and drone, check they stand upright, are not mirrored, and the skids or dishes line up with the heading.

**Good.** Cabs point the way the heading says.

**Bad.** Cabs point the opposite way (180 degrees off), or sideways (90 degrees off), or models lie on their side. Write it down and ask an agent.

**What to write.**

```text
- [HUMAN] Date: 2026-11-19
- [HUMAN] Result per entity: vehicle PASS cab on heading; mast PASS upright; uas PASS skids on heading
```

#### Feeder task: validate and export one asset from the panel (gate G5)

Gate G5 also needs you to use the Blender panel once by hand. Do it now, it takes two minutes.

1. Open Blender with the extension (Part 1.9).
2. Open `ent_vehicle_wheeled_a.blend`, make its collection active, press "Validate Asset". Good: all rows pass.
3. Press "Export Asset". Good: no error. It writes into `assets\entities\ent_vehicle_wheeled_a\export\`.
4. Close Blender without saving.
5. In the terminal, run `git status`. If the export files show as changed, the export was not byte-identical. Run `git diff --stat` to see how much. If you do not want to keep the change, run `git checkout assets/entities` to undo it.

There is no separate log line for this. You can mention it in the front-direction result, for example "panel validate and export done".

#### Feeder task: review the generated tokens

**What it is.** You decide whether the three placeholder models are good enough to tell apart.

**Steps.**

1. In Blender, open each of the three `.blend` files and press "Validate Asset". All must pass.
2. Run `uv run tilepipe entities` (needs Blender, about half a minute). Good: `3 entities, 19 deliverable checks, 0 errors` near the end.
3. Do the distance test in 4.5.

**If a token is hard to recognize,** do not edit the model by hand. The fix is to change the part sizes in the spec's entity table and in `blender/scripts/make_entities.py`, then regenerate. Ask an agent.

There is no separate log line. It feeds the art lock.

### 4.5 Art-lock hashes

**What it is.** You do three looking tests, freeze the two look files in `look/`, and write down their fingerprints.

**Why it matters.** It proves the colors in the video and screenshots are the exact ones in the repo.

**Before locking you may change looks.** You may change any value in `look/opaque.json` or `look/additive.json`. After any change, run `uv run tilepipe validate` and check that LOOK-01 to LOOK-05 still pass in the report. Once you write the hashes, do not touch these files again.

**The three tests.**

1. **Squint test.** Look at H1 and H2 with your eyes half closed. Good: the entities are the first thing you notice. Bad: the terrain or lines grab your eye first.
2. **Grayscale test.** Make a gray copy of H1, outside the repo:

```powershell
ffmpeg -i docs\img\h1_workstation_opaque.png -vf format=gray $env:TEMP\h1_gray.png
explorer $env:TEMP\h1_gray.png
```

   Good: in gray you can still tell apart the entities, the thick index contours, the thin minor contours, and the grid.
3. **Distance test.** Show H5 full screen. Stand 2 m away. Good: you can tell which is the truck, the mast, and the drone. Bad: you cannot. Then see "review the generated tokens" above.

**Take the hashes.**

PowerShell:

```powershell
Get-FileHash look\*.json -Algorithm SHA256 | Format-List Hash, Path
```

Git Bash:

```bash
sha256sum look/*.json
```

PowerShell prints capital letters, Git Bash small letters. Both are the same hash. If you did not change the look files, today's values are:

```text
additive.json  7d6c9beedf1000872ad061b276328ff195c5d1cdec31d215659c03288c0ab044
opaque.json    42d4a4fcb6d98f0ee91779ec6115c7337b6bc3ff74fbf416eeac1b6cc72da26f
```

**What to write.** File names only, no folder path from the drive:

```text
- [HUMAN] Date: 2026-11-19
- [HUMAN] Hashes of `look/*.json`: opaque 42d4a4fc...a26f, additive 7d6c9bee...b044; squint, grayscale, distance PASS
```

Writing the full 64 characters is safest. Shortening saves words if you hit the word limit; if you shorten, say so.

### 4.6 Drill rehearsals

**What they are.** Four exercises you must do twice each, cleanly, without help, so you can do them live.

**Why it matters.** They show you control the pipeline yourself.

"Clean" means: no mistakes, no looking things up, the result matches what is expected.

#### Feeder task before D4: rewrite each "why" in `docs/DECISIONS.md`

1. Open `docs/DECISIONS.md`.
2. Find every line that says `- Why: DRAFT, for Bradd to write in his own words.` (there are 11 for D1 to D11, and more under Deviations, 23 in all).
3. Replace each one with your own reason in one or two sentences. Example: `- Why: A grid gives predictable triangle counts and streams simply.`
4. Read each record aloud as if answering a question in drill D4.
5. Done when no `DRAFT` word is left. Check with:

```powershell
Select-String -Path docs\DECISIONS.md -Pattern DRAFT
```

Good: no output. Remember Part 0: one test will then fail until it is updated.

#### D1. Retarget a budget (target 90 seconds)

1. Build once and start the viewer in a second terminal.
2. Run:

```powershell
uv run tilepipe profile set-share mobile_ar 0.08
```

   Good: the `[budget]` lines in `profiles\mobile_ar.toml` now read frame 60000, terrain 36000, entities 18000, draw calls 6.
3. Run:

```powershell
uv run tilepipe build --from batch
uv run tilepipe validate
```

   Good: `validate` exits 1 and shows `SCN-02 FAIL profile:mobile_ar: measured 8 draws, limit <= 6 draws`. The terrain error grows (an earlier audit saw `e_star` go from about 29.6 m to about 53.5 m). Entities still pass.
4. Open `profiles\mobile_ar.toml`, find `[terrain]`, change `batch = "quadrant"` to `batch = "tile"`, save. Run step 3 again. Good: 5 draws in all, verdict PASS, exit 0.
5. Run `uv run tilepipe site`, then reload the viewer and press `2`. Good: new terrain selection, new error, new budget bars. (The spec skips the `site` step, but the viewer reads copies made by `site`, so you need it.)
6. Undo:

```powershell
git checkout profiles/mobile_ar.toml
uv run tilepipe all --no-blender
git status
```

   Good: `git status` shows no changed tracked files.

#### D2. Break and fix an asset (target 90 seconds)

1. Open `ent_vehicle_wheeled_a.blend` in Blender with the extension. Press "Validate Asset". All pass.
2. Click the LOD 0 object (`ent_vehicle_wheeled_a_LOD0`). Press `N`, Item tab, set Scale to 100, 100, 100. Press "Validate Asset". Good: ENT-03 fails, shows the measured scale and a fix hint. Click that row: the object gets selected and framed.
3. Press `Ctrl` + `Z` until the scale is back to 1. Validate: all pass. Press "Export Asset".
4. Close Blender without saving. Run `git status` and undo any export change you do not want (see 4.4 feeder task).

#### D3. Build a new place (only if Mount St. Helens was built)

This drill needs the St. Helens source data committed in `data/source/`. Today only the Anza-Borrego file is there, so this optional extra was not built. You cannot rehearse it. Write "not run, P1.1 not built".

#### D4. Defend a decision (2 minutes each)

1. Pick a record in `docs/DECISIONS.md`. Say out loud: the decision, why, the rejected alternative, and when you would revisit it.
2. Practise at least D2 (grid), D4 (shading from textures), D5 (height in two 8-bit channels), and D10 (where budgets come from), plus the question "Did you write this code?".
3. Time yourself. Good: each under 2 minutes, without reading.

**What to write.** For each drill, two dates:

```text
- [HUMAN] D1 retarget budget, rehearsal 1 and 2: 2026-11-19 clean, 2026-11-20 clean
- [HUMAN] D2 break fix an asset, rehearsal 1 and 2: 2026-11-19 clean, 2026-11-20 clean
- [HUMAN] D3 build new place, rehearsal 1 and 2: not run, P1.1 not built
- [HUMAN] D4 defend decisions, rehearsal 1 2: 2026-11-19 clean, 2026-11-20 clean
```

### 4.7 Video claims check

**What it is.** After you record and edit your walkthrough video (at most 3 minutes), you watch it with the report open, and check that every number and claim you say is in the report and is true.

**Why it matters.** One wrong number in a video destroys trust. Anything you cannot match must be cut from the video.

**Steps.**

1. Open the report: `http://127.0.0.1:8000/report/`.
2. Play the video. Pause at every number or claim.
3. Find it in the report. Two numbers the script leaves blank:
   - The build time: run `uv run tilepipe all` (with Blender) and read `total_seconds` in `build\anza_borrego_01\build_info.json`. Say the number you see.
   - The mobile terrain error in pixels: in the report, search `TER-09`. Today it says 12.7338 px for `mobile_ar`.
4. Also check: no music, only your voice, any sped-up part is labeled on screen.

**Good.** Every claim matched. **Bad.** Any claim not in the report. Cut it and re-edit.

**What to write.**

```text
- [HUMAN] Date: 2026-11-21
- [HUMAN] Result: PASS, every spoken number matched the report
```

Uploading the video, setting it in `site/config.json`, and making the repo public are outward actions in gate G7. They are yours alone.

### 4.8 Approved threshold changes

**What it is.** A list of times when you agreed to bend a rule. Five items are already written below the line. An agent wrote them, recording what you agreed on 2026-11-17. The audit could not confirm them, because only you can.

**Why it matters.** Nothing may quietly loosen a rule. Your confirmation is the record that you agreed.

**What each item means, in plain words, and how to confirm it.**

1. **The download time stays in `tile.json`.** It is when the USGS data was downloaded, not when you built. It never changes between builds. Confirm: open `dist\anza_borrego_01\tile.json`, search `retrieved_utc`. It says `2026-11-14T19:08:49Z`. Build again. It is still the same.
2. **The standard Blender install folder is written in exactly one code file.** Confirm:

```powershell
git grep -l -F "Blender Foundation" -- "*.py" "*.toml" "*.json"
```

   Good: only `src/tilepipe/cli.py`.
3. **A profile with warnings but no failures counts as PASS.** The warning count is shown next to it. Confirm: in the viewer's Budget panel, the validation chip reads like "PASS, 1 warning". In the report, TER-09 rows still say WARN.
4. **`build_info.json` records the Blender and GDAL versions.** Confirm: open `build\anza_borrego_01\build_info.json`. Good: `"blender_version": "5.2.0 LTS"` and `"gdal_version": "3.12.2"`.
5. **The offline check covers the whole `all` command.** Confirm, PowerShell:

```powershell
$env:TILEPIPE_OFFLINE = "1"
uv run tilepipe all
$LASTEXITCODE
Remove-Item Env:TILEPIPE_OFFLINE
```

   Git Bash: `TILEPIPE_OFFLINE=1 uv run tilepipe all; echo $?`. Good: `0`. An earlier audit measured about 73 seconds.

**What to write.** Replace the placeholder line `- [HUMAN] None approved, or list each with date and reason:` with your confirmation, and leave the five items below it as they are:

```text
- [HUMAN] Items 1 to 5 below approved 2026-11-17, confirmed by Bradd 2026-11-19
```

If you disagree with any item, write that instead, and ask an agent. Undoing one may need code changes.

---

## Part 5. Suggested order

1. Part 0, then Part 1.1 to 1.4 (install, preflight, build).
2. 4.1 AOI sign-off and 4.2 MGRS. These are gate G1 and come first.
3. Start the viewer. Do the bench capture and the browser checks (4.3).
4. Blender: install the extension, panel validate and export, token review, front direction (4.4).
5. If you want to change colors, do it now. Then take the six screenshots and make `assets\fallback.jpg`.
6. Art lock: three tests and hashes (4.5).
7. Rewrite every `DRAFT` why in `docs/DECISIONS.md`.
8. Confirm the five approved changes (4.8).
9. Drills D1, D2, D4, twice each, on two different days if you can (4.6).
10. Record the video, then the claims check (4.7).
11. Ask an agent to update the three document tests (Part 0). Run `uv run pytest -q`. Good: all pass.
12. Gate G7 (upload, publish, phone test) is yours alone.

## Part 6. Final checklist

- [ ] Preflight all PASS
- [ ] AOI sign-off: date and result written
- [ ] MGRS: both strings, date, result written
- [ ] Viewer in every browser checked, versions written
- [ ] Probe reading exact, cursor within 10 m
- [ ] Network shows only `127.0.0.1:8000`
- [ ] `bench.json` saved in `build\anza_borrego_01\`, SCN-04 PASS, pacing written
- [ ] Six screenshots in `docs\img\`, each 1920 by 1080
- [ ] `assets\fallback.jpg` made from H1
- [ ] Panel validate and export done once in Blender, `git status` checked
- [ ] Three tokens recognizable from 2 m
- [ ] Front direction per entity written
- [ ] Squint, grayscale, distance tests passed
- [ ] Look hashes written, look files not touched since
- [ ] No `DRAFT` left in `docs/DECISIONS.md`
- [ ] Five approved changes confirmed, placeholder line replaced
- [ ] D1, D2, D4 rehearsed twice clean and logged; D3 marked not run
- [ ] Video claims check written
- [ ] Three document tests updated, `uv run pytest -q` all pass
- [ ] No drive paths, username, or email in `docs/VERIFICATION.md`

---

## Part 7. Where the spec and the code disagree

The code is what actually runs, so trust the code. These are the differences found while writing this guide:

1. **The log tests block filling the log.** See Part 0. Three tests fail as soon as you do your human tasks. This is the main blocker.
2. **Word limit.** `docs/VERIFICATION.md` is capped at 400 words by a test. Filling every line probably goes over.
3. **Pictures folder.** The spec places your table photo and fallback picture under the viewer's assets. The code reads `assets/room.jpg` and `assets/fallback.jpg` from the repo root `assets` folder.
4. **`site/config.json`.** The spec says it holds only the video link. The code also writes `aoi` and `repo_url`. At publish time you must fill both `video_url` and `repo_url`.
5. **Drill D1 step 5.** The spec says "reload the viewer". You must also run `uv run tilepipe site` first, or the viewer shows the old data.
6. **Drill D3.** It needs the Mount St. Helens data, which was not built. It cannot be rehearsed.
7. **No log lines** for the pacing fraction, the 10-second first-frame check, or the panel export. This guide puts short notes on the browser and front-direction lines instead.
8. **Report date.** The spec says the report header shows the build date. The code shows the source download date instead, so two builds give the same report (recorded as D-13).
9. **The approved changes in 4.8** were written by an agent, not by you. They count only once you confirm them.
