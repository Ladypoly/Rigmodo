// SPDX-License-Identifier: MIT
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Editor
{
    [Serializable] public class BoneMapping { public string bone; public string human; }
    [Serializable] public class ClipManifest
    {
        public string name, file, root_motion_policy;
        public int frame_start, frame_end;
        public float fps;
        public bool loop;
    }
    [Serializable] public class CharacterManifest
    {
        public int schema_version;
        public string profile, character, fbx_sha256, skeleton_signature;
        public string artifact_kind, source_model, source_model_sha256;
        public BoneMapping[] mapping;
        public ClipManifest[] clips;
    }
    [Serializable] public class CalibrationNode
    {
        public string name; public Vector3 position; public Quaternion rotation; public Vector3 scale;
    }
    [Serializable] public class CharacterValidation
    {
        public string asset, unity_version, skeleton_signature;
        public bool valid_avatar, human_avatar;
        public int mapped_bones, skinned_meshes, blendshapes;
        public float height_meters;
        public CalibrationNode[] calibration;
    }

    // Explicit menu operation: unrelated FBX imports and subsequent user overrides are untouched.
    public static class CharacterImporter
    {
        [MenuItem("Assets/Local Character/Configure Selected Export for Unity")]
        public static void ConfigureSelected()
        {
            string path = AssetDatabase.GetAssetPath(Selection.activeObject);
            try
            {
                var manifest = ReadManifest(path);
                if (manifest.artifact_kind == "animation") AnimationImporter.Configure(path);
                else Configure(path);
            }
            catch (Exception ex) { Debug.LogError("Local Character: " + ex.Message); }
        }

        public static CharacterValidation Configure(string assetPath)
        {
            if (!assetPath.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Select the exported character FBX");
            var manifest = ReadManifest(assetPath);
            if (manifest.artifact_kind == "animation") throw new InvalidDataException("Use animation configuration for this FBX");
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) throw new InvalidDataException("Asset is not a model import");
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (model == null) throw new InvalidDataException("Import the FBX before configuring it");
            CalibrationNode[] calibration;
            using (var preview = new ModelPreview(model))
            {
                var clone = preview.Root;
                var transforms = clone.GetComponentsInChildren<Transform>(true);
                var duplicate = transforms.GroupBy(t => t.name).FirstOrDefault(g => g.Count() > 1);
                if (duplicate != null) throw new InvalidDataException("Ambiguous transform name: " + duplicate.Key);
                var byName = transforms.ToDictionary(t => t.name);
                if (manifest.profile == "HUMANOID")
                {
                    var byHuman = new Dictionary<string, Transform>();
                    var human = new List<HumanBone>();
                    foreach (var mapping in manifest.mapping)
                    {
                        if (!byName.TryGetValue(mapping.bone, out var transform))
                            throw new InvalidDataException("Missing exported bone: " + mapping.bone);
                        if (!Enum.TryParse(mapping.human, out HumanBodyBones id) || id == HumanBodyBones.LastBone)
                            throw new InvalidDataException("Invalid human identity: " + mapping.human);
                        if (byHuman.ContainsKey(mapping.human)) throw new InvalidDataException("Duplicate human identity: " + mapping.human);
                        byHuman.Add(mapping.human, transform);
                        human.Add(new HumanBone { boneName = mapping.bone, humanName = HumanTrait.BoneName[(int)id], limit = new HumanLimit { useDefaultValues = true } });
                    }
                    // Calibrate a disposable clone, never alter source FBX geometry or its bind matrices.
                    Vector3 up = (byHuman["Head"].position - byHuman["Hips"].position).normalized;
                    Vector3 left = Vector3.ProjectOnPlane(byHuman["LeftUpperArm"].position - byHuman["RightUpperArm"].position, up).normalized;
                    if (left.sqrMagnitude < .9f) throw new InvalidDataException("Cannot determine shoulder direction");
                    foreach (string side in new[] { "Left", "Right" })
                    {
                        Vector3 direction = side == "Left" ? left : -left;
                        Align(byHuman[side + "UpperArm"], byHuman[side + "LowerArm"], direction);
                        Align(byHuman[side + "LowerArm"], byHuman[side + "Hand"], direction);
                    }
                    var description = new HumanDescription
                    {
                        human = human.ToArray(),
                        skeleton = transforms.Select(t => new SkeletonBone { name = t.name, position = t.localPosition, rotation = t.localRotation, scale = t.localScale }).ToArray(),
                        upperArmTwist = .5f, lowerArmTwist = .5f, upperLegTwist = .5f, lowerLegTwist = .5f,
                        armStretch = .05f, legStretch = .05f, feetSpacing = 0, hasTranslationDoF = false
                    };
                    importer.animationType = ModelImporterAnimationType.Human;
                    importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    importer.humanDescription = description;
                }
                else if (manifest.profile == "GENERIC")
                {
                    importer.animationType = ModelImporterAnimationType.Generic;
                    importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    importer.motionNodeName = "Root";
                }
                else throw new InvalidDataException("Unknown export profile");
                calibration = transforms.Select(t => new CalibrationNode { name = t.name, position = t.localPosition, rotation = t.localRotation, scale = t.localScale }).ToArray();
            }
            importer.globalScale = 1;
            importer.useFileScale = true;
            importer.optimizeGameObjects = false;
            importer.preserveHierarchy = true;
            importer.skinWeights = ModelImporterSkinWeights.Custom;
            importer.maxBonesPerVertex = 4;
            // Tested Unity 6.3/6.4 import validation restores smaller values
            // to .001. The Blender export copy uses this same explicit floor.
            importer.minBoneWeight = .001f;
            importer.importBlendShapes = true;
            importer.importAnimation = false;
            importer.SaveAndReimport();
            model = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            var avatar = AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<Avatar>().FirstOrDefault();
            var renderers = model.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            var result = new CharacterValidation
            {
                asset = assetPath, unity_version = Application.unityVersion, skeleton_signature = manifest.skeleton_signature,
                valid_avatar = avatar != null && avatar.isValid, human_avatar = avatar != null && avatar.isHuman,
                mapped_bones = manifest.mapping.Length, skinned_meshes = renderers.Length,
                blendshapes = renderers.Sum(r => r.sharedMesh.blendShapeCount), calibration = calibration,
                height_meters = CombinedHeight(renderers)
            };
            if (manifest.profile == "HUMANOID" && (!result.valid_avatar || !result.human_avatar))
                throw new InvalidDataException("Unity rejected the Humanoid Avatar; review joints/calibration");
            string output = Path.ChangeExtension(assetPath, ".unity-validation.json");
            File.WriteAllText(output, JsonUtility.ToJson(result, true));
            AssetDatabase.ImportAsset(output);
            Debug.Log("Local Character configured: " + assetPath);
            return result;
        }

        public static CharacterManifest ReadManifest(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath) || !assetPath.StartsWith("Assets/", StringComparison.Ordinal) || !assetPath.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Select an exported FBX under Assets");
            string manifestPath = Path.ChangeExtension(assetPath, ".character.json");
            if (!File.Exists(manifestPath)) throw new FileNotFoundException("Missing sibling character manifest", manifestPath);
            var manifest = JsonUtility.FromJson<CharacterManifest>(File.ReadAllText(manifestPath));
            if (manifest == null || manifest.schema_version != 1 || manifest.mapping == null)
                throw new InvalidDataException("Unsupported character manifest");
            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                string hash = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(assetPath))).Replace("-", "").ToLowerInvariant();
                if (hash != manifest.fbx_sha256) throw new InvalidDataException("FBX differs from its export manifest; export a new matching bundle");
            }
            return manifest;
        }

        static void Align(Transform parent, Transform child, Vector3 direction)
        {
            Vector3 segment = child.position - parent.position;
            if (segment.sqrMagnitude < 1e-10f) throw new InvalidDataException("Zero-length calibration segment: " + parent.name);
            parent.rotation = Quaternion.FromToRotation(segment, direction) * parent.rotation;
        }
        static float CombinedHeight(SkinnedMeshRenderer[] renderers)
        {
            if (renderers.Length == 0) return 0;
            Bounds bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            return bounds.size.y;
        }
    }
}
