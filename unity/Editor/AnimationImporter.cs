// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Editor
{
    [Serializable] public class AnimationValidation
    {
        public string asset, source_model, skeleton_signature, clip, unity_version;
        public bool human, loop;
        public float duration_seconds, frame_rate;
    }

    public static class AnimationImporter
    {
        public static AnimationValidation Configure(string assetPath)
        {
            var manifest = CharacterImporter.ReadManifest(assetPath);
            if (manifest.artifact_kind != "animation" || manifest.clips == null || manifest.clips.Length != 1)
                throw new InvalidDataException("Expected one selected-Action animation manifest");
            string source = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(assetPath), manifest.source_model ?? ""));
            string bundle = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(assetPath), "..")) + Path.DirectorySeparatorChar;
            if (!source.StartsWith(bundle, StringComparison.OrdinalIgnoreCase) || !source.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Animation source must be a character FBX in the same bundle");
            string project = Path.GetFullPath(".") + Path.DirectorySeparatorChar;
            if (!source.StartsWith(project, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Source model is outside this project");
            string sourceAsset = source.Substring(project.Length).Replace('\\', '/');
            var sourceManifest = CharacterImporter.ReadManifest(sourceAsset);
            if (sourceManifest.artifact_kind == "animation" || sourceManifest.skeleton_signature != manifest.skeleton_signature ||
                sourceManifest.fbx_sha256 != manifest.source_model_sha256 || sourceManifest.profile != manifest.profile)
                throw new InvalidDataException("Animation does not match the exported character hierarchy, rest pose, profile and file hash");
            var avatar = AssetDatabase.LoadAllAssetsAtPath(sourceAsset).OfType<Avatar>().FirstOrDefault();
            bool human = manifest.profile == "HUMANOID";
            if (!human && manifest.profile != "GENERIC") throw new InvalidDataException("Unknown animation rig profile");
            if (avatar == null || !avatar.isValid || avatar.isHuman != human)
                throw new InvalidDataException("Configure the source character Avatar before its animation");
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) throw new InvalidDataException("Animation FBX is not imported");
            var clip = manifest.clips[0];
            if (clip.fps <= 0 || clip.frame_end <= clip.frame_start || clip.root_motion_policy != "preserve_bone_motion")
                throw new InvalidDataException("Unsupported clip timing or root-motion policy");
            importer.animationType = human ? ModelImporterAnimationType.Human : ModelImporterAnimationType.Generic;
            importer.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
            importer.sourceAvatar = avatar;
            importer.globalScale = 1; importer.useFileScale = true;
            importer.importAnimation = true; importer.optimizeGameObjects = false;
            importer.preserveHierarchy = true;
            // Preserve evaluated keys for the initial import; compression is an explicit later choice.
            importer.animationCompression = ModelImporterAnimationCompression.Off;
            if (!human) importer.motionNodeName = "Root";
            var takes = importer.defaultClipAnimations;
            if (takes.Length != 1) throw new InvalidDataException("Expected exactly one FBX take");
            var take = takes[0];
            take.name = clip.name; take.loopTime = clip.loop; take.loopPose = false;
            take.keepOriginalOrientation = true; take.keepOriginalPositionXZ = true; take.keepOriginalPositionY = true;
            take.lockRootRotation = false; take.lockRootPositionXZ = false; take.lockRootHeightY = false;
            take.heightFromFeet = false;
            importer.clipAnimations = new[] { take };
            importer.SaveAndReimport();
            var clips = AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<AnimationClip>().Where(c => !c.name.StartsWith("__preview__")).ToArray();
            if (clips.Length != 1 || clips[0].name != clip.name || clips[0].isHumanMotion != human)
                throw new InvalidDataException("Unity did not import the selected clip with the expected rig type");
            var imported = clips[0];
            float expected = (clip.frame_end - clip.frame_start) / clip.fps;
            if (Mathf.Abs(imported.length - expected) > 1 / clip.fps + 1e-4f)
                throw new InvalidDataException("Imported clip duration differs from the selected Action");
            var result = new AnimationValidation { asset = assetPath, source_model = sourceAsset, skeleton_signature = manifest.skeleton_signature,
                clip = imported.name, human = human, loop = clip.loop, duration_seconds = imported.length, frame_rate = imported.frameRate,
                unity_version = Application.unityVersion };
            string output = Path.ChangeExtension(assetPath, ".unity-validation.json");
            File.WriteAllText(output, JsonUtility.ToJson(result, true)); AssetDatabase.ImportAsset(output);
            Debug.Log("Local Character animation configured: " + assetPath);
            return result;
        }
    }
}
