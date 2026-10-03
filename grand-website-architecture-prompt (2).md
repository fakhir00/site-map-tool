# GRAND WEBSITE ARCHITECTURE BUILD PROMPT

Build the intent-led architecture below for the browser-based circuit diagram editor. This revised local plan replaces the earlier keyword-driven page list; it does not claim a live SERP review or change published URLs.

## Website context

- Primary query: circuit diagram maker.
- Primary action: create and export electronic circuit diagrams in the browser.
- Audience: students, electronics engineers, hobbyists and educators.
- Supplied capabilities: drag-and-drop schematic editing, electronic symbols, Manhattan wire routing, SVG/PNG/JSON export, auto-save, keyboard shortcuts, offline operation and responsive design.
- Product conveniences belong in the editor documentation: grid snapping, keyboard shortcuts, routing, symbol-library coverage, auto-save, LocalStorage and dark mode. Describe only implemented behavior; do not infer new capabilities from a keyword.
- Outside product scope: PCB physical layout, circuit simulation, programming, IT networking and real-time collaboration.
- JSON sharing is file-based sharing. Local storage is local persistence. Neither implies simultaneous multi-user editing.

## Architecture rules

Do not create a URL just because a keyword exists. Follow:

KEYWORD → SEARCH INTENT → USER PROBLEM → ENTITY/TOPIC → CONTENT REQUIREMENT → URL DECISION

Every page = enough content to completely satisfy its unique intent.

Final spoke count is determined by semantic validation, distinct search intent, product capability, and unique user value. There is no minimum or target URL count.

Normalize obvious wording and word-order variations. A coherent user need owns one URL. Modifiers such as free, online, simple, easy and web do not earn pages unless they materially change the task and required answer.

Before adding a URL, compare the same user, task, answer, expected SERP intent and entity with existing resources. If most answers are yes, keep the phrase on the existing page. Assess expected intent conservatively; no live SERP evidence is supplied here.

Feature phrases containing “with X”, “for X”, “using X”, “X maker” or “X symbol” require assessment. A small component belongs in a relevant section. A major feature or entity still needs an independent task and unique useful content before receiving a page.

## MASTER HUB: Circuit Diagram Maker

- Primary keyword: circuit diagram maker.
- URL: `/`.
- Purpose: primary product page and editor entry point. Own the exact-match core query and let the user draw a schematic immediately.
- User problem: create, edit, save and export a circuit diagram without installing a desktop editor.
- Content requirement: working editor entry, supported symbol and connection behavior, brief usage guidance, export choices and accurate persistence behavior.
- Supporting phrases: electronic circuit diagram maker, circuit schematic diagram maker, free circuit diagram maker, free online circuit diagram maker, online circuit diagram maker free, schematic diagram maker online free, electronic circuit app when referring to this browser editor.
- Feature sections: grid snapping; keyboard shortcuts; Manhattan routing; available symbols; auto-save and LocalStorage; appearance controls. Do not create separate indexable pages for these conveniences.
- Sharing/storage section: explain supported JSON export/import and local persistence. Clarify here that real-time collaboration is not supported. Do not create a collaboration landing page or add collaboration implementation requirements.
- Navigation: present the product first, then major use cases, major resources and selected high-value supporting pages.
- Resource entries: Symbols, How to Draw, and Examples. Add further navigation only when it helps users reach a validated resource.
- Scope boundary: link to the full symbol reference, drawing tutorial and example collection rather than repeating their complete content.

## RESOURCE: Circuit Diagram Symbols

- Target keyword: circuit diagram and symbols.
- URL: `/circuit-diagram-and-symbols/` (retain the existing planned path).
- Parent: homepage.
- Intent: identify and interpret schematic notation.
- User problem: recognize a component symbol, its terminals and its meaning before drawing or reading a circuit.
- Unique value: a visual reference organized by component function, with labels and applicable notation differences.
- Content requirement: recognizable symbols, names, meanings and terminal conventions. Distinguish general reference information from symbols actually available in the editor.
- Supporting phrases: schematic symbols, common schematic symbols, circuit component symbols, symbol names and abbreviations.
- Sections: common components, power connections, connectors, operational amplifiers and logic-gate symbols where useful. Explain IEC/ANSI differences within the reference when supported by accurate material.
- URL decision: reference lookup differs from operating the editor or following a drawing lesson. Individual symbol libraries and notation modifiers remain sections until distinct user value is demonstrated.
- Contextual links: drawing tutorial for applying notation; examples for seeing symbols in context; editor when the reader is ready to draw.

## GUIDE: How to Draw Circuit Diagrams

- Target keyword: how to draw circuit diagrams.
- URL: `/circuit-tutorial/` (retain the earlier tutorial destination).
- Parent: homepage.
- Intent: learn a repeatable drawing workflow.
- User problem: turn a circuit idea into a readable schematic with clear connections and labels.
- Unique value: a worked sequence that teaches component placement, wiring, junctions, labels and readability checks.
- Content requirement: one complete drawing walkthrough, common drawing mistakes and supported save/export steps. Explain what the editor does and what must be checked manually; do not imply simulation or automatic electrical validation.
- Supporting phrases: circuit tutorial, circuit tutorial overview, electrical circuit drawing, draw circuit diagram, creating circuit schematic.
- Sections: plan components; choose symbols; connect and label; check readability; save/export. Mention relevant shortcuts or routing controls in the step where they help.
- URL decision: instruction differs from the tool itself and from looking up a symbol. Tutorial/overview wording does not justify multiple pages.
- Contextual links: symbols at the notation step, examples for practice, editor for carrying out the workflow.

## RESOURCE: Circuit Examples

- Target keyword: circuit examples.
- URL: `/circuit-examples/`.
- Parent: homepage.
- Intent: find an understandable reference schematic to study or adapt.
- User problem: start from an example rather than a blank canvas.
- Unique value: annotated circuit examples with a stated purpose, component labels and an explanation of connections.
- Content requirement: a small, useful selection of accurate examples organized by circuit purpose. Explain each diagram sufficiently to understand or redraw it. Do not promise tested hardware performance or simulated results without evidence.
- Supporting phrases: simple circuit diagram, simple electronic circuit diagram, simple electrical circuit diagram, electric circuit diagram, circuit diagram and schematic electronic circuit where the query seeks an example or explanation.
- Sections: foundational series/parallel examples; LED examples; selected digital/analog examples when suitable. These are collection sections initially, not an instruction to create one URL per circuit.
- URL decision: choosing and understanding an example is distinct from learning the general drawing process or identifying a symbol. Broad diagram wording does not earn another generic page.
- Contextual links: symbols used in each example, the tutorial for drawing steps, and the editor for adapting an example.
- Deeper pages: create only if a particular example needs a distinct, independently useful explanation that this resource cannot adequately provide. Reapply the one-page test first.

## Consolidation decisions

| Earlier proposal | Decision | Reason |
|---|---|---|
| Electronic Circuit Diagram Maker; Circuit Schematic Diagram Maker; Electronic Circuit App | Homepage sections/supporting phrases | Same browser schematic-creation task |
| Circuit Diagram Simulator | Remove from the build plan | Simulation is unsupported |
| Circuit Visualizer | No dedicated page | No distinct supported visualization workflow established; drawing belongs to the editor, simulation is out of scope |
| Circuitlab Examples | Remove from the build plan | Another product's examples are not this product's resource |
| Schematic Electronic Circuit; Simple Circuit Diagram; Electric Circuit Diagram; Simple Electronic Circuit Diagram; Simple Electrical Circuit Diagram; Circuit Diagram | Cover applicable explanation/example needs in Circuit Examples | Current briefs do not establish independent tasks for these generic diagram variants |
| Electrical Circuit Drawing; Circuit Tutorial Overview | Drawing tutorial | Same instructional workflow |
| Digital Circuit Tutorial; Analog Circuit Tutorial | Relevant example or drawing sections initially | Current briefs do not establish sufficiently distinct instructional scope within the product's drawing purpose |
| Grid snapping; keyboard shortcuts; Manhattan routing; 40 symbols; auto-save; LocalStorage; dark mode | Relevant editor/documentation sections | Product conveniences rather than independent topical clusters |
| Real-time collaboration | No dedicated page | Unsupported; clarify only in relevant JSON-sharing/local-storage guidance |

These are editorial decisions based on the supplied product scope and existing briefs. Do not turn the old loose keyword buckets into mandatory coverage: circuit simulation, PCB layout, programming, third-party products and unrelated electronics problems remain outside this plan.

## Interlinking strategy

The homepage presents the product and routes users to major use cases, major resources and selected high-value supporting pages. Topical hubs handle deeper relationships.

Symbols links to relevant drawing guidance and examples. The drawing guide links to notation and examples at the steps where they help. Examples link to relevant symbol explanations and drawing steps. Link back to the editor when the next task is to create or edit a diagram. Use descriptive anchors and avoid a sitewide footer listing every page.

## DO NOT CREATE DEDICATED PAGES FOR THESE KEYWORDS

These phrases may still occur naturally where semantically appropriate. They must not be assigned as standalone SEO targets unless later evidence demonstrates a genuinely distinct search intent.

- Free/online/order variants of circuit diagram maker, including schematic diagram maker online free.
- Minor editor-feature variants such as circuit diagram maker with grid snapping or dark mode.
- Individual symbol-library modifiers already satisfied by the symbols resource.
- Generic diagram and tutorial variants consolidated above.

Unsupported capabilities remain excluded even when demand exists. Mention them only to explain a relevant limitation; do not imply the product provides them.

## Existing URL handling

This file is a plan, not evidence that the former proposed URLs are published. Omit removed draft URLs from the build and internal links. If any are already live, verify their content and destination before implementing redirects or changing the sitemap. Preserve the retained resource paths, and consolidate the duplicate product entry at `/circuit-diagram-maker/` into `/` if that old path exists.
