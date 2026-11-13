# Animation controls

In **Rigmodo → Motion → Animations**, use the arrow to search existing Actions whose bone channels match the selected rig. The current Action name is editable in the same row. Selecting a clip resets unkeyed bone transforms and updates the preview range; authored loops omit the duplicated endpoint during playback.

**+** creates a named empty Action in rest pose for manual pose keys. Previous Actions are retained. **Generate Motion** below the library remains the way to create a new AI animation; successful results appear in the picker without a separate import step.

The trash button asks for confirmation and deletes only the selected Action. Shared Actions, NLA references and linked Actions are protected. It does not remove rigs, meshes or other clips. Switching and editing are blocked while a model job is running.

Empty clips retain their owner across saving and reopening the file. Animated Actions are matched by bone channel names, including the correct slot in multi-slot Actions; matching names do not retarget motion between different skeleton proportions. The picker also works for Actions created before these controls were installed.

Checks: `tests/motion_clips_acceptance.py` covers selection, loop ranges, empty clip creation and persistence, shared/NLA deletion protection, multi-slot filtering, stable picker values, invalid names and object preservation. `tests/loop_preview_acceptance.py` checks existing preview behavior.

## Playback

Each Action has a **Loop** checkbox. Attack and death clips default to playing once; walk, run, crawl and idle clips default to repeating. The artist can override the setting. **Preview Motion** starts playback. One-shot previews stop at the last frame and hold that pose; normal Timeline playback also respects the setting for Rigmodo-managed clips. Loop previews omit an authored duplicate endpoint. Clips selected in Rigmodo and newly generated clips retain their playback choice when renamed. The same choice controls the Unity export loop flag.

This controls playback and export intent. It does not remove repeated movements already generated inside an Action or create new contact corrections.
