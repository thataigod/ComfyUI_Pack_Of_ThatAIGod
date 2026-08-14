# Character Object System — Plan (Current State)

Status:
* **Camera** — DONE, committed (`35b6a3c`, `e79b812`, `269cd0f`).
* **Character** — DONE, committed (`8e152ee` + follow-up fixes `0112e9b`/`15936ca`/`eaeb0bf`/`ba40c3d`, the modifier pipeline `13d0680`, the wardrobe curation `1163bfb`, the auto-skip `c60cc1b`). This document rides with the Character commits.
* **Scene** — v2 rebuild implemented in the working tree (engine, node, data, UI, tests); pending its single Scene v2 commit.

## Architecture

```
Resolution node ──> Camera ──> CAMERA object ──> Character (stripping) ──> CHARACTER object ──> Scene ──> scene Description
                        │                                                        │
                        └────────────── CAMERA object (regions/view) ─────────────┘
```

The Camera→Character link is the CAMERA **object** (`regions`, `face_visible`, `view` — Character never reads the camera's prose). Each node emits its own Description; the user reorders and combines the three components downstream (Scene v2 never composes a combined Full Prompt).

Three nodes, each emitting an object twin + prose. The camera owns shot geometry; the character owns identity, pose, state and outfit; the scene (future) owns location, time and style layers.

---

## Camera node contract

**Inputs (5):** `Width` · `Height` · `Seed` · `Wildcard Mode` (Deterministic (Seed) / Full Auto / Random (No Repeat)) · `Camera Config` (hidden JSON, managed by `js/camera.js`).

**Outputs (5):** `Description` (STRING) · `Keywords` (STRING) · `Camera` (CAMERA object) · `Camera JSON` (STRING) · `Visible Regions` (STRING).

**Axes (6):** shot size, camera angle, view, movement, dutch tilt, render look.

| Axis | Options |
|---|---|
| Shot Size | Extreme Close-Up, Close-Up, Medium Close-Up, Medium, Cowboy, Medium Full, Full, Long, Extreme Long |
| Camera Angle | Eye Level, Low Angle, High Angle, Top Down, Worm's Eye |
| View | Front, 3/4 Front, Profile, 3/4 Back, Back |
| Movement | Static, Pan, Tilt, Tracking, Handheld |
| Tilt | None, Slight, Strong |
| Look | 15 camera bodies/stocks (film/digital families) |

**Option space is file-driven:** `wildcards/camera/<axis>/*.txt` — one file per option with `#@` directives (`lens`, `depth`, `close`, `regions`, `elevation`, `hides`, `azimuth`, `roll`, `family`, `keyword`, `shortcuts`, `name`, `based_on`). **Replace semantics per axis:** the axis folder replaces that axis's built-ins wholesale; an option must resolve by its own name (if it matches a built-in) or via `#@based_on` pointing at a built-in, otherwise it is skipped. Missing or empty axis folders fall back to the built-in tables; `_`/`.`-prefixed files are ignored. The frontend fetches the effective space + shortcut groups from `GET /that_aigod/camera_options`.

**Selection semantics:** single = fixed; subset = seeded roll / no-repeat cycle within it; All = whole space; **empty = axis unrestricted** — its clause is omitted from prose and keywords entirely (no shot-size clause, no lens/depth, no look sentence; geometry stays honest for the remaining axes). Legacy configs without a key fall back to the full list.

**Geometry honesty:** visible regions = shot-size set − angle hides − view hides; elevation 90° implies overhead geometry (no face, no headroom phrasing); movement phrasing is stills-safe and size-scaled (close vs wide buckets); composition phrases are size/angle aware. Keywords use model-friendly override maps.

**CAMERA object keys:** type, shot_size, angle, view, movement, tilt, look, side, lens, depth_of_field, orientation, azimuth, elevation, roll, face_visible, regions, composition, description, keywords, width, height.

---

## Character node contract

**Inputs (7):** `Persona` (dropdown from `wildcards/characters/`, female/male guaranteed) · `Camera` (CAMERA object) · `Use Common Wardrobe` (BOOLEAN, **default False**) · `Use Shared Garment Modifiers` (BOOLEAN, default True) · `Seed` · `Wildcard Mode` (Deterministic (Seed) / Random (No Repeat)) · `Character Config` (hidden JSON `{"occasions": [...], "states": [...]}`, managed by `js/character.js`). Legacy `Occasion` dropdown values are still accepted.

**Outputs (6):** `Character` (CHARACTER object) · `Character JSON` · `Description` · `Keywords` · `Occasion` (STRING) · `Trigger` (STRING).

**Occasion semantics:** All (default) = seeded roll of a covered occasion; subset = roll/cycle within it; single = fixed; **None (empty list) = truly unrestricted** (no `#@occasion` filtering, no roll, Scene receives `""`); absent key = All. The resolved occasion is emitted on the Occasion pin.

**State axis (5 values):** dressed, revealing, mishap, slipping, nude.
* Auto (default): occasion-weighted roll — default 70/12/8/5/5; intimate/boudoir 30/20/15/15/20; office/formal/wedding 95/3/2/0/0. A proper subset rolls uniformly within it; single is fixed; an empty, full or absent states list means Auto (weighted roll).
* **Revealing**: sheer/translucent clause from `shared/state-revealing.txt`.
* **Mishap**: per-garment `#@mishap:` phrase wins, else `shared/state-mishap.txt` fallback.
* **Slipping**: per-garment `#@slip:` phrase wins, else `shared/state-slip.txt`.
* **Nude**: outfit replaced by the persona's region-tagged `nude.txt` (one seeded pick per visible `#@regions` block — geometry-honest: back views never mention nipples).

**Fit prose:** persona `measurements.txt` declares zone adjectives (shipped personas: female `#@bust: full / #@waist: slim / #@hips: curved`, male `broad / lean / narrow`; local-only personas may differ, e.g. Rohini's `generous / tiny / flared`); garments declare `#@fit:` zones (tops bust/waist, bottoms waist/hips, one-piece bust/waist/hips); the engine composes a seeded per-zone clause ("fitting snugly over her generous bust") gated on the zone's region being visible, gender-aware ("his broad chest"). Defaults apply when measurements are missing.

**Conditions:** garments declare `#@condition: wet|sweaty|clinging`; eligible garments roll ~25% for a clause from `shared/state-condition.txt` (a wool sweater can never be wet).

**Pose honesty:** the camera owns facing. The pose file's `#@facing:` vocabulary (front / three-quarter / profile / back / back three-quarter) is asserted from the camera view; `#@gaze:` lines are blocked (via the `"unavailable"` sentinel value) whenever the face is out of frame; `#@awareness:` stays free. A persona with no line for the active facing degrades gracefully (falls back without the facing gate, but the gaze block survives). Profile views substitute the persona's `profile.txt` for `face.txt`.

**Outfit gating:** the resolved outfit category joins the resolution context, so attribute files (e.g. `hair.txt`) can gate variants on the active category via `#@outfit:` directives.

**Wardrobe:** the persona's own `wardrobe/` wins when it has a `catalog.txt`; otherwise the matching default persona's wardrobe (`characters/<gender>/wardrobe`) is used only when `Use Common Wardrobe` is on (default off). Categories declare `#@occasion`; garment slots fill only for visible regions; tagless **garment slots** (tops, bottoms, one-piece — never shoes or accessories) may receive a shared garment-style modifier; one-piece substitutes tops+bottoms at 50%.

**Trigger:** `trigger.txt` (one token per line) resolves as a plain seeded pick; carried on the object (`trigger` key) and the Trigger pin — **never** in description or keywords.

**CHARACTER object keys:** type, persona, trigger, state, occasion, regions, face_visible, attributes (fixed 20-key schema), pose, outfit_category, outfit, subject, description, keywords.

**Persona schema (23 files):** subject_intro, gender, profile, pose, measurements, nude + 17 region attributes (face, hair, neck, shoulders, back, body, breasts, navel, arms, hands, waist, hips, buttocks, thighs, legs, feet, skin). `body.txt` is the figure; `breasts.txt` the bust. `hair.txt` may carry `#@outfit` variant blocks (a directive-free first block is the universal default). `nude.txt` uses front-exclusive `#@regions` blocks (breasts / navel / back / buttocks / thighs / legs, feet + a universal "fully nude" lead line), so an MCU says just "fully nude" and a back view never mentions nipples.

**Garment modifier pipeline:** every tagless garment in tops/bottoms/one-piece draws **color, pattern, fabric and design** clauses from the shared decks (`colors.txt` with "in X", `pattern.txt` and `design.txt` phrase-ready, `fabric.txt` with "with X") in declared order. Categories narrow the list via `#@modifiers:` on the category file (curated per wardrobe); category fabric decks (`garment-style-<category>.txt`) win over the generic for sensible fabrics. **Auto-skip:** a garment that names its colour, fabric or pattern skips that dimension automatically (denim stays denim; a white blouse never gets a random colour) while the rest still varies. Explicit controls per garment: `#@fixed: true` (nothing appended — reserved for identity pieces such as a classic black tuxedo, armour, matching sets), `#@modifiers:` (override the list), `#@no_modifiers:` (subtract dimensions). Garment control directives are **block-scoped**: they apply only to the line they sit above, never leaking to the next garment.

---

## Scene node (v2 plan)

Scene v2 is the final composer, but **it no longer combines**: the user reorders the three components (Character description, Camera description, Scene description) downstream per model/lora. The node emits only its own prose.

### Contract

**Inputs:** `Occasion` (dropdown: auto / All (unrestricted) / explicit value) · `Location` (Auto or an explicit `wildcards/scenes/` file) · `Time of Day` (All or a `#@time` value) · `Use Film Look` (BOOLEAN, default True) · `Seed` · `Wildcard Mode` (Deterministic (Seed) / Random (No Repeat)) · optional `Character` (CHARACTER object — supplies occasion/state/outfit context only). **Removed:** Subject, Camera, Use Atmosphere, Use Lighting.

**Outputs:** `Scene` (SCENE object) · `Scene JSON` (STRING) · `Description` (STRING — location + time + film prose only, no subject/camera) · `Keywords` (STRING — location key + time value). **Full Prompt is removed.**

### Engine rules

1. **State-aware gating (strict):** when the wired CHARACTER's state is non-dressed (`nude`, `slipping`, `mishap`, `revealing`), eligible locations are limited to scenes that declare the state via `#@state:` plus universal (directive-less) scenes such as the studio. Public scenes can never host non-dressed states.
2. **Time/setting blocks:** scene files are stacked directive blocks (`#@time:` + `#@setting:` per block, like `shared/time-of-day.txt`); the existing resolver filters lines by the active context. **Anti-contradiction contract:** scene blocks own fixtures, furniture, mood and place nouns — never sun, sky, stars or time names; the time phrase owns all light/sky/shadow quality. Doubled "golden hour" and "bright blue sky at golden hour" become structurally impossible. Every `#@time` value in a scene's header has a matching block; each scene keeps one time-neutral fallback block (no `#@time`) for `All` and unexpected times.
3. **Layers:** atmosphere and lighting layers are removed from the engine and their content folds into scene blocks where applicable. The film look remains a single layer over the `film-look` decks.
4. `#@setting` is read from the picked scene and filters the time phrase indoor/outdoor (unchanged from v1).

### Film-look data (`wildcards/styles/film-look/`)

One file per family, deduplicated, all long-form "Style and tones: …" entries (104 total): `commercial-stocks.txt` (23) · `soviet-stocks.txt` (19) · `ddr-stocks.txt` (8) · `tonality-grades.txt` (8) · `era-looks.txt` (20) · `digital-looks.txt` (15) · `analog-processes.txt` (8) · `quality.txt` (3). A single deck `wildcards/styles/film-look.txt` references the families. The v1 style residue (`all-device`, `all-composition`, `all-lighting`, `composition`, `camera-position-optics`, `moment-motion`, `focus-depth`, `flash-photography`, `lighting`, `atmosphere`, `film-stocks`, `soviet-film`, `ddr-film`, `digital-snapshots`, `the-misc-bin`, `color-tonality`, `decades`, `quality`, `all-film`) is deleted (the whole `styles/` tree is untracked, so this is clean). The `autowildcards/` folder is the old wardrobe system and holds no film data — untouched.

### Scene data

- All 15 scene files rewritten as time/setting blocks with fixtures-only prose; `#@state: nude, slipping, revealing, mishap` on the private scenes (bedroom, boudoir).
- Gap fill: `home` (living room), `costume` (convention hall), `traditional` (heritage courtyard), `resort` (villa/poolside), daytime `festival` (street fair), `city_day`, night variants for beach/pool/park, and `dawn`/`blue hour`/`midnight` scene coverage.
- `shared/time-of-day.txt` keeps its structure and all `#@time` values; minor prose polish only where tests do not pin the phrase.

### UI

`js/scene.js` — live description widget only (no chips; Location and Time stay single-value dropdowns).

### Tests

The scene suites are updated to the new contract and extended with: state gating, block-time filtering, contradiction scans (no sun/sky/time words in scene prose; no duplicated time values), film-deck structure (families non-empty, deduplicated), and the removed inputs/outputs. Full suite stays at 100% coverage with ruff + mypy clean.

### Commit

One **Scene v2 commit**: `_scene_core.py`, `Scene.py`, `js/scene.js`, `wildcards/scenes/`, `wildcards/styles/`, `tests/test_scene*`, `__init__.py` (Scene registration). Plan doc updated; `wildcards/README.md` stays deferred; Rohini stays local.

---

## Scene node (v1 notes — superseded)

The v1 implementation consumed the CHARACTER object's `occasion`, `outfit_category` and `description`, plus the CAMERA's `description`/`keywords`; locations came from `wildcards/scenes/` filtered by `#@occasion`/`#@time`/`#@outfit`; `#@setting` was read from the picked scene and filtered the time-of-day phrase. It was flawed: state-blind location selection (nude fell to the studio even for intimate occasions), a film layer that doubled up with the Camera's look, embedded-time contradictions in scene prose, no home/costume/traditional scenes, and no frontend. All of this is replaced by the v2 plan above.

---

## Directive vocabulary

Known keys (`_wildcard_core.KNOWN_DIRECTIVE_KEYS`): occasion, scale, regions, outfit, setting, time, location, facing, gaze, elevation, roll, awareness, context, preset, fit, condition, mishap, slip, modifiers, no_modifiers, fixed, state.

Asserted by the Character engine: `regions` (always), `occasion` (when set), `outfit` (resolved category), `facing` (camera view), `gaze` (blocked via the `"unavailable"` sentinel when the face is hidden), `condition` (the rolled per-garment condition before picking from the state-condition deck). Asserted by the Scene engine: `occasion`, `time`, `outfit` and `state` (location selection). Everything else is author metadata until a consumer asserts it.

---

## Files

| File | Role |
|---|---|
| `_wildcard_core.py` | shared directive-aware resolver: parse/accumulate, eligibility, deep tag checks, no-repeat decks (per-file, per-context, per-block salt), `pick_line_with_directives` (block-scoped), `pick_line_per_block`, `_block_directives` |
| `_camera_core.py` | camera engine: axis tables, option-space loader, geometry, prose + keyword composers, bag |
| `Camera.py` | Camera node + `/that_aigod/camera_options` route |
| `js/camera.js` | camera chips UI |
| `_character_core.py` | character engine: persona resolution, pose/fit/state/nude, wardrobe + modifier pipeline, occasion roll |
| `Character.py` | Character node + `/that_aigod/character_options` route |
| `js/character.js` | character chips UI (occasions + states) + info widget |
| `_scene_core.py` | scene engine: state-aware location gating, time/setting block selection, film layer |
| `Scene.py` | Scene node (no combined output — description only) |
| `js/scene.js` | scene info widget |
| `wildcards/camera/` | camera option files |
| `wildcards/characters/female/`, `male/` | default personas + their wardrobes |
| `wildcards/scenes/` | scene files as time/setting blocks (`#@state` on private scenes) |
| `wildcards/styles/` | film-look families (one deck over 8 family files) |
| `wildcards/shared/` | occasions, colors/pattern/fabric/design decks, garment-style-<category> decks, state decks, time-of-day |
| `tests/` | engine + node suites (currently 751 passing, 100% coverage) |

## Decisions

- Camera owns facing and framing; Character never contradicts it (pose + nude + fit are geometry-honest).
- Option spaces and personas are file-driven; built-ins remain the offline fallback.
- Empty selections mean "unrestricted", not "everything" — absent keys mean "everything".
- Everything is deterministic (seeded) or deck-cycled; no AI, no LLM calls.
- Garment variety beats fixation: the pipeline varies colour/pattern/fabric/design on every safe garment; garments that name a dimension auto-skip it, and only true identity pieces (tuxedo, armour, matching sets) are explicitly fixed.
- Garment control directives are block-scoped — they never leak to the next garment.
- Scene v2 never combines components: each node emits its own Description and the user reorders them downstream.
- Scene locations are state-honest (non-dressed states stay private) and time-honest (scene blocks never carry sun/sky/time words).
- Adult content is first-class (explicit personas, nude state, revealing/mishap/slipping) but always region-honest.
- Rohini Smirnova is a local-only persona (gitignored, never committed).
- `wildcards/README.md` has been rewritten in the working tree but its commit stays deferred until all nodes are done.
