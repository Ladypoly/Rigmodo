# Processing feedback

Rigmodo 0.13 adds viewport-only effects while its local jobs run. Cyan joint pulses mark rigging, mint bone comets and a moving scan ring mark skinning, violet trails mark motion, and amber accents mark image posing. Provider setup uses the same status display without decorating a character. Successful jobs give a short green pulse; cancellation, failure and a workflow requiring review stop the effects without a success signal.

The sidebar and Extension Settings show one shared stage/elapsed-time/Cancel panel. Stage names come from the running worker. Elapsed time covers the operation, including workflow stage changes. The moving ring is an activity indicator, not a percentage or remaining-time estimate. Cancel is a request consumed by the existing owning modal or image timer; it follows the same cancellation path as Escape and never applies unfinished results.

Under **Extension Settings → Defaults → Viewport feedback**, disable **Processing effects** or enable **Reduced animation**. Reduced mode uses static accents with one update per second. Blender's Overlay toggle, object visibility, local view and scene scope are respected. Overlays do not appear in final renders or exports.

The renderer creates no objects, materials, modifiers, keyframes or rig helpers. It caches bone endpoints and bounding boxes, follows pose/object transform changes through bounded read-only snapshots, and uses two line batches for the character. It never evaluates mesh vertices, scans weights, reads inference logs or polls/completes workers. Bone sampling is capped at 192, mesh bounds at 64 objects, and forced redraws at eight per second. Shader/batch references and draw handlers are released when finished. There is no processing timer when idle, and no GPU batches when the relevant viewport is hidden, effects are disabled or Blender overlays are off. Native viewport navigation can redraw more often than the effect timer.

These limits apply to the overlay. Redrawing an expensive Blender scene still incurs that scene's normal rendering cost; Reduced animation or disabling effects avoids the extra redraw cadence. Python drawing also pauses during Blender's synchronous result application or deformation check, then resumes/stops when Blender returns to its event loop.

## Verification, 5 October 2026

The private 6,598-vertex avatar passes a real SkinTokens → regional refinement → quality check → in-place commit through Skin Avatar, with the overlay running throughout asynchronous stages. Source object identities, rest joints, Action and object/data/collection counts remain stable. A second actual workflow is cancelled through the new shared Cancel operator, preserving the accepted character. Successful effects remove their own timer and handlers.

Final visual tests draw all four effects through Blender's actual GPU handlers, check exact GPU-state restoration, cached geometry, Blender Overlay/Reduced/disabled behavior and load/undo cleanup. Read-only preview effects preserve geometry, weights, pose, frame, object identity and transforms. The four preview jobs are simulations, separately labelled from the real skin run. Native image-drop/apply/Undo/Redo/ordinary Kimodo pose keys/stale-frame/shared-cancel regression passes with a simulated SAM worker using the existing MHR fixture; SAM and Kimodo neural inference themselves use the unchanged prior baseline.

On the tested RTX 4090 machine, final previews draw at most 496 vertices. Warm batch building takes 0.214 ms median / 0.310 ms p95; maximum observed world-overlay and HUD CPU draw times are 0.235 / 0.433 ms. These are callback timings, excluding Blender's scene rendering and model inference, not a physical 16 GB hardware or whole-scene GPU utilization guarantee.

The user's live Blender reload preserves all five objects, the selected Rigmodo_Rig_Motion, Generated Motion Action, pose and frame 803. See `processing-visuals-acceptance-2026-10-05.json` and `processing-visuals-live-2026-10-05.json`. Tests and private screenshots remain outside the distributable; no character assets are committed.
