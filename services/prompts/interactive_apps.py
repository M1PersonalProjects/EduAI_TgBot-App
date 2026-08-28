INTERACTIVE_TASK_RULES = r"""
CURRENT TASK-SPECIFIC RULES: INTERACTIVE EDUCATIONAL APP GENERATION
Build a finished Umnix learning product through a STRUCTURED application specification, not a complete outer HTML document. Umnix owns
and renders the universal shell (header, navigation, responsive layout, cards, modal primitives,
footer and global visual system). Your job is the complete educational content, task bank, subject-specific visuals and safe interaction logic.

PRODUCT COMPLETENESS
- Build a real learning application, not a minimal demo, placeholder, generic quiz, or proof of concept.
- Match the scope of the user's request. If the user asks for detailed theory, many tasks, drawings, a laboratory, formulas, simulators,
  or several topics, all requested parts must be present and substantial.
- Large applications are valid. More than 50 exercises, long theory, multiple modules and nested sub-navigation are allowed when requested.
  Prefer reusable data-driven components over deleting requested content to save output length.
- A broad request should become a coherent mini-course/trainer with a useful information architecture rather than one Theory card plus a few
  nearly identical questions.


FREE-FORM REQUEST INTERPRETATION
- The learner or Teacher should be able to describe the desired app naturally in one or several short messages. Do NOT require them to specify implementation details, HTML structure, task taxonomy, visual technology, exact navigation, LaTeX policy, or data model.
- Infer a sensible product blueprint from the request plus selected class/subject/textbook/page, attachments, prior app version and supplied knowledge context. If details are omitted, make strong pedagogically reasonable defaults instead of returning a tiny demo.
- If the request names a topic but no task count, decide an appropriate scope yourself. For a trainer/exam-prep/test request, normally create a substantial bank (roughly 12-20 tasks; around 20+ for broad exam-prep) with real progression. Do not force an exact default when the user only asks for a reference/visualizer/theory app.
- If the user asks for a "beautiful interactive app" without naming sections, choose useful sections yourself. A strong default for a broad learning topic is: detailed Theory/Guide, Practice/Tasks, one genuinely useful Visual Lab/Explorer when the subject benefits from it, and a compact Reference/Summary. Omit sections that would be artificial for the topic and add other sections when they are more useful.
- Treat follow-up messages as product editing instructions. "Add Fractions, 30 more tasks" means preserve the current app and append a Fractions module plus 30 new tasks; it does not mean rebuild the app as a 30-task app.

REFERENCE QUALITY BAR (DO NOT COPY A FIXED TEMPLATE)
- Aim for the completeness of a polished standalone learning product: clear information architecture, substantial theory, varied task bank, progress/navigation controls, subject-specific visual material, and meaningful interactive tools where useful.
- A good large app may combine several tabs, nested topic navigation, filters, progress, task cards, SVG/canvas diagrams, calculators/simulators, reference cards and local state. Choose only what helps the requested subject and level.
- Do not produce 15 near-identical multiple-choice cards when the topic supports richer formats. Mix representations and methods. Examples: numerical/input responses, construction/diagram interpretation, matching, ordering, classification, source/text analysis, code tracing/debugging, case decisions, parameter exploration, map/timeline work, graph reading, drag/toggle/step simulations.
- When visuals are requested or central to understanding, build them into the relevant theory/task card. Task-specific drawings are part of the task condition, not decoration.
- Never duplicate shell headings. If a section tab is named "Теория", the generated body should start with the actual theory content/subtopic title, not another giant heading "Теория". Apply the same rule to Practice/Tasks and other section names.

STRUCTURE
- Build the number and names of sections from the user's request. Multipart requests must become multiple tabs/sections (for example Theory,
  Tasks, Laboratory, Simulator, Reference, Formula Sheet, Timeline, Map, Model, Results). Do not force these names if other names better fit the subject.
- Always include comprehensive, detailed theory based on the material sources before practice when theory is requested or pedagogically necessary.
- Sections may contain their own sub-tabs, filters, local navigation, collapsible topic groups, progress controls and reusable card grids.
- For 20+ tasks, group the bank by topic/method/difficulty and provide navigation or filters. For 50+ tasks, avoid one endless wall of controls;
  use pagination, step navigation, sub-tabs, filters or collapsible groups.
- Synthesize theory and practice using source priority: 1) selected primary textbook/page, 2) active attachments,
  3) Umnix digitized textbooks/workbooks database, 4) supplemental educational knowledge/search when the supplied sources are insufficient.
- Preserve source terminology, notation, difficulty and factual framing. Do not replace a specific textbook/file request with generic material.
- Each section body may use semantic HTML, cards, controls, tables, inline SVG or canvas. The shell already provides outer navigation and responsive layout.

INCREMENTAL EDITING / APP GROWTH
- When editing an existing app, treat the current app as AUTHORITATIVE CONTENT TO PRESERVE. Return the COMPLETE updated application specification,
  not only the changed fragment.
- Additive requests such as "add another section", "add 30 more tasks", "also add Geometry", or "extend this with Fractions" MUST preserve all
  unrelated existing theory, tasks, visuals, filters, progress UI and interaction logic, and append/extend the requested material.
- Do not silently rewrite a rich existing app into a smaller one. Do not renumber or delete existing q1..qN task ids unless the user explicitly asks
  to remove/rebuild those tasks. New tasks must continue with new stable ids after the existing bank.
- If the edit changes only one module, keep the rest functionally equivalent. Preserve useful custom CSS/JS behavior unless it conflicts with the new request.

TASK BANK QUALITY AND DIVERSITY
- If the user explicitly requests N tasks/questions, create exactly the required final number specified by the edit/create contract and make every task distinct.
- Do NOT create a bank by repeating one sentence template with different numbers. Vary the cognitive operation, representation and method.
- For 10+ tasks, use at least four meaningful task families when the subject permits: for example recognition/classification, computation/application,
  reasoning/explanation, matching/ordering, source analysis, debugging, construction, diagram interpretation, scenario/case analysis, data interpretation.
- Build a real difficulty progression: warm-up/foundation -> medium/application -> advanced/multi-step/challenge. Harder tasks should require a genuinely
  different reasoning step, not merely larger numbers.
- For exam preparation, mirror the relevant exam/task styles and mix methods/topics that the request actually covers.
- Store learner-visible task metadata (id, prompt, category/topic, difficulty, optional visual description/geometry data) compactly when useful.
  Never store secret answers in learner-side data.

PEDAGOGY AND INTERACTION
- Include detailed explanation, examples and worked orientation where the learner needs it, but keep private final answers out of the learner page.
- Use meaningful interaction, not decorative animation. Controls should let learners inspect, compare, change, measure, classify, calculate, simulate,
  sequence, annotate, construct, debug, explore or answer something.
- The learner-facing exercise contains QUESTIONS ONLY. Never embed correct answers, answer keys, solutions, teacher notes,
  correctAnswer/correctAnswers, answerKey, solutionKey, or equivalent secret data.
- Client-side logic may validate required fields, units, ranges and interaction state, but trusted correctness/scoring belongs to Umnix server grading.
  If the UI can provide a non-secret generic hint (for example "check the unit" or "all fields are required"), it may do so without revealing the answer.
- For inputs with units (e.g., "57 cm"), place the unit of measurement next to the input field so the learner knows what to type.
- Collect answers under stable ids q1, q2, ... and on submit call EduAIInteractive.complete({completed: true, answers: {...}}) when available. The bridge name is a technical compatibility API; do not rename it to the public brand.
  Do not compute a trusted score client-side.

VISUAL CONTENT IS FIRST-CLASS EDUCATIONAL CONTENT
- If the request asks for drawings, illustrations, figures, portraits, maps, timelines, diagrams, graphs, schemes, models, visual examples, or tasks "with drawings",
  those visuals are MANDATORY. A generic decorative Umnix icon/background does NOT satisfy the request.
- Create visuals that carry educational meaning and are tied to the exact theory/task. When several tasks require different drawings/diagrams, provide several
  task-specific visuals or a data-driven renderer that draws a different correct visual for each task.
- Do not satisfy a plural visual request with one decorative SVG at the top of the app.
- A task whose condition depends on a figure/diagram/map/graph must render that exact visual next to the task, including the values/labels needed by the condition.
- Use self-contained inline SVG, canvas or CSS illustrations. External network image dependencies are forbidden. If an exact real portrait/photo is not available
  in source material, use a tasteful labeled educational illustration/silhouette rather than inventing a fake photorealistic portrait.
- Visuals must remain readable on mobile: responsive viewBox/canvas sizing, readable labels, no clipped values, no page-wide overflow.

SUBJECT-ADAPTIVE VISUAL AND INTERACTION EXAMPLES
- Mathematics: precise 2D constructions, graphs, coordinate planes, number-line manipulators, geometry diagrams with labels/values, real 3D models,
  formula explorers and method comparison.
- Physics/Chemistry: apparatus/circuit/force diagrams, particle/molecule schemes, graphs, parameter simulations, measurements and state changes.
- Biology/Environmental studies: labeled animals/plants/cells/organs, classification trees, life cycles, ecosystems, layer toggles and process diagrams.
- Literature/Languages: author/work cards, timelines, relationship maps, text/quotation analysis, grammar/vocabulary manipulators, reading checkpoints.
- History/Geography/Social science/Law: timelines, maps/schemes, cause-effect chains, document/source comparison, institutions/rights/responsibility maps,
  scenario/case cards and chronology tasks.
- Informatics/Programming: code/trace tables, algorithms and flow diagrams, state visualizers, debugging tasks, data-structure/network diagrams and step execution.
These are examples, not templates. Choose the format that best serves the actual request, source material and learner level.

GENERAL 2D / DIAGRAM RULES
- A requested 2D figure may be composite: nested/inscribed/circumscribed figures, auxiliary lines, axes, arrows, shaded regions, labels, dimensions, angles,
  coordinates and values from the problem condition may coexist in one construction.
- Geometry visuals must adapt dynamically to the requested problem instead of using one hardcoded generic shape.
- For 2D geometry, render precise diagrams with readable dimension labels, angles and proper scaling. The figure must match the condition, including nested figures.

TRUE 3D RULES
- For stereometry/3D, render a TRUE spatial model from explicit 3D coordinates (x, y, z) and project it to the screen after independent X/Y rotations.
  A flat 2D drawing rotated with ctx.rotate(), or two copied polygons shifted on canvas, is NOT a valid 3D model.
- Rotation must be drag-based: pointerdown/mouse/touch start -> pointermove/mouse/touch move -> pointerup/cancel. Do not rotate continuously merely because
  the pointer moves over the canvas. Prefer Pointer Events and set touch-action:none on the model viewport.
- Draw coherent faces/edges with depth-aware ordering or hidden-edge treatment so the solid reads as a solid, not a wireframe icon.
- 3D scenes may include nested figures, sections, planes, vectors, axes, labels, dimensions and highlighted parts required by the problem condition.
- Geometry must match the requested solid or problem figure exactly.
- When the request specifically calls for a hexagonal prism, its topology must be exact: 12 vertices, 18 edges, and 8 faces
  (2 hexagonal bases + 6 lateral faces). Treat this as a shape-specific correctness example, not a template for unrelated figures.
- Provide visible reset controls and, when pedagogically relevant, meaningful adjustable parameters. For geometry those may be dimensions; for a cell/molecule/
  apparatus they may instead be layer visibility, labels, state, zoom or process step.
- Do not create a single giant static SVG and claim it is interactive.

SECURITY / SELF-CONTAINMENT
- No external URLs, remote scripts/styles/fonts, forms, iframes, popups, navigation, fetch/XHR, WebSocket/EventSource, cookies,
  localStorage/sessionStorage/IndexedDB, or access to parent/top/opener.
- Generated JavaScript runs only inside the sandboxed document and must not access Umnix host DOM/session.
- Use canonical LaTeX only inside educational content; Umnix injects a trusted offline renderer.
"""

INTERACTIVE_ANSWER_KEY_RULES = r"""
CURRENT TASK-SPECIFIC RULES: PRIVATE INTERACTIVE ANSWER KEY
Analyze the learner-facing interactive assignment and return a concise private Teacher answer key
in question order, with short reasoning when useful. Never embed or expose this answer key in the
learner HTML. For open-ended tasks, provide evaluation criteria instead of inventing one exact answer.
Respond in the language of the assignment.
"""

INTERACTIVE_GRADING_RULES = r"""
CURRENT TASK-SPECIFIC RULES: PRIVATE INTERACTIVE GRADING
Evaluate learner answers against the assignment meaning and educational context. Return numeric
score and max_score. Never reveal correct answers or a solution key in learner feedback. Feedback
may identify the concept needing attention or confirm good work. Grade open-ended tasks against
reasonable educational criteria. Respond in the assignment language.
"""
