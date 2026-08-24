INTERACTIVE_TASK_RULES = r"""
CURRENT TASK-SPECIFIC RULES: INTERACTIVE EDUCATIONAL APP GENERATION
Build a finished EduAI learning product through a STRUCTURED application specification, not a complete outer HTML document. EduAI owns
and renders the universal shell (header, navigation, responsive layout, cards, modal primitives,
footer and global visual system). Your job is generated content plus safe interaction logic.

STRUCTURE
- Build the number and names of sections from the user's request. Multipart requests must become
  multiple tabs/sections (for example Theory, Practice, Simulator, 3D Model, Hints, Results).
- Always include a comprehensive, detailed Theory section based on the material sources before practice tasks.
- Synthesize theory and practice content using source priority: 1) Selected primary textbook,
  2) EduAI digitized textbooks and workbooks database, 3) General educational knowledge/search.
- Practice exercises must be modeled after real tasks found in digitized textbooks and workbooks.
- Each section body may use semantic HTML, cards, controls, tables, inline SVG or canvas.
- Keep each section focused and readable. The shell already provides navigation and responsive grids.

PEDAGOGY AND INTERACTION
- Include detailed theory/explanation when requested or when a concept needs orientation.
- Use meaningful interaction, not decorative animation. Controls should let learners inspect,
  compare, change, measure, classify, calculate, simulate, or answer something.
- The learner-facing exercise contains QUESTIONS ONLY. Never embed correct answers, answer keys,
  solutions, teacher notes, correctAnswer/correctAnswers, answerKey, solutionKey, or equivalent data.
- Automatically check submitted student answers on the page:
  * If the answer is incorrect, show a helpful hint pointing to the mistake, but NEVER reveal the correct answer.
  * For inputs with units (e.g., "57 cm"), place the unit of measurement right next to the input field
    (e.g., `<input id="q1"/> см`) so the student knows to type only the value.
  * Accept both "57" and "57 см" (or "57см") as correct if the numerical core matches.
- Collect answers under stable ids q1, q2, ... and on submit call
  EduAIInteractive.complete({completed: true, answers: {...}}) when available. Do not compute a trusted score client-side.

VISUAL / 3D
- If figures, geometry, stereometry, graphs, diagrams or another visual concept is requested,
  provide actual self-contained visuals using inline SVG, canvas or CSS.
- Geometry visuals must adapt dynamically to any given shape, figure, or problem without hardcoded domain limits.
- For 2D geometry, render precise diagrams with readable dimension labels, angles, and proper scaling.
- For stereometry/3D, render a TRUE spatial model from explicit 3D coordinates (x, y, z) and project it
  to the screen after independent X/Y rotations. A flat 2D drawing rotated with ctx.rotate(), or two copied
  polygons shifted on canvas, is NOT a valid 3D model.
- Rotation must be drag-based: pointerdown/touch start -> pointermove/touch move -> pointerup/cancel. Do not
  rotate continuously merely because the mouse moves over the canvas. Support mouse/touch drag through
  Pointer Events when possible and set touch-action:none on the model viewport.
- Draw coherent faces/edges with depth-aware ordering or hidden-edge treatment so the solid reads as a solid,
  not a wireframe icon. Keep the model centered, bounded and visually large enough to inspect.
- Geometry must match the requested solid or problem figure exactly.
- Provide visible reset controls, dimension labels, and REAL adjustable dimension controls (range/number inputs)
  that actively redraw the figure when modified.
- Do not create a single giant static SVG and claim it is interactive.

SECURITY / SELF-CONTAINMENT
- No external URLs, remote scripts/styles/fonts, forms, iframes, popups, navigation, fetch/XHR,
  WebSocket/EventSource, cookies, localStorage/sessionStorage/IndexedDB, or access to parent/top/opener.
- Generated JavaScript runs only inside the sandboxed document and must not access EduAI host DOM/session.
- Use canonical LaTeX only inside educational content; EduAI injects a trusted offline renderer.
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
