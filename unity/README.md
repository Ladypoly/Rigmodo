# Rigmodo Unity companion 0.9.0

Extract this archive to `Assets/LocalCharacter` in Unity 6.3 LTS. Editor and Runtime folders must both be present. Assembly definitions isolate the editor tools from game scripts; the runtime assembly contains only the opt-in forearm twist component. Remove older copies of the same companion classes before placing another version at a different path.

Copy complete Blender-exported bundles into Assets. Select the character FBX and use **Assets → Rigmodo → Configure Selected Export for Unity**. Configure its animation FBX afterward. Re-run only when you intend to apply the exported profile: this command sets mapping, four weights, uncompressed initial animation and exposed bone transforms explicitly.

For generated Humanoid motion, use the editable `.anim` created/selected by the companion. Its explicit motion curves preserve the Blender Root trajectory. Use Animator root motion for traveling playback; in-place clips suit game-controller locomotion. The embedded FBX clip alone can drift under Unity's body projection. Existing edits to generated `.anim` assets survive reconfiguration.

Optional twists: select a configured twist-enabled Humanoid character and choose **Create Humanoid Playback Prefab with Twists**. This creates a new prefab in isolation; it does not change an open scene or the FBX. Basic Humanoid rigs need no runtime component. Generic animation already bakes helpers. Arrange any custom late IK to run before the twist component or update helpers explicitly afterward. Transform optimization must remain disabled/expose the required bones.

Character and clip manifests verify file hashes and matching hierarchy/rest pose. Do not rename/move individual bundle components independently. Missing textures, arbitrary Blender materials, facial/shape-key animation and modifier baking require separate authoring work. Joint placement and skin quality still need visual review.

Code: MIT, see LICENSE. This companion contains no AI model weights or private characters.
