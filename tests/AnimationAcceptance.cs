// SPDX-License-Identifier: MIT
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace LocalCharacter.Tests
{
    public static class AnimationAcceptance
    {
        [Serializable] public class Result
        {
            public string name, error;
            public bool passed;
            public float generic_lbs_error_meters, root_travel_meters, hand_movement_meters, finger_rotation_degrees;
            public AnimationValidation validation;
        }
        [Serializable] public class Sample { public float time; public Vector3[] points; }
        [Serializable] public class Reference { public Sample[] samples; public float root_travel; }

        public static List<Result> Evaluate(string fixtureRoot)
        {
            var results = new List<Result>();
            var generic = new Result { name = "SelectedActionGeneric" };
            try
            {
                string modelPath = fixtureRoot + "/SyntheticMotionGeneric/SyntheticMotionGeneric.fbx";
                string clipPath = fixtureRoot + "/SyntheticMotionGeneric/Animations/SelectedWave.fbx";
                CharacterImporter.Configure(modelPath);
                generic.validation = AnimationImporter.Configure(clipPath);
                var clip = AssetDatabase.LoadAllAssetsAtPath(clipPath).OfType<AnimationClip>().Single(c => !c.name.StartsWith("__preview__"));
                var reference = JsonUtility.FromJson<Reference>(File.ReadAllText(fixtureRoot + "/SyntheticMotionGeneric/animation-reference.json"));
                using (var preview = new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath)))
                {
                    var clone = preview.Root;
                    var bones = clone.GetComponentsInChildren<Transform>(true).ToDictionary(t => t.name);
                    Vector3 hips = bones["Hips"].position;
                    Vector3 up = (bones["Head"].position - hips).normalized;
                    Vector3 left = (bones["LeftArm"].position - bones["RightArm"].position).normalized;
                    Vector3 forward = -Vector3.Cross(left, up).normalized;
                    Vector3 startRoot = Vector3.zero;
                    for (int i = 0; i < reference.samples.Length; i++)
                    {
                        var sample = reference.samples[i]; clip.SampleAnimation(clone, sample.time);
                        if (i == 0) startRoot = bones["Root"].position;
                        var actual = new List<Vector3>();
                        foreach (var renderer in clone.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                        {
                            var mesh = new Mesh();
                            try
                            {
                                renderer.BakeMesh(mesh);
                                foreach (var vertex in mesh.vertices)
                                {
                                    Vector3 delta = renderer.transform.TransformPoint(vertex) - hips;
                                    actual.Add(new Vector3(Vector3.Dot(delta, left), Vector3.Dot(delta, forward), Vector3.Dot(delta, up)));
                                }
                            }
                            finally { UnityEngine.Object.DestroyImmediate(mesh); }
                        }
                        float error = 0;
                        foreach (var point in actual) error = Mathf.Max(error, sample.points.Min(p => (p - point).magnitude));
                        foreach (var point in sample.points) error = Mathf.Max(error, actual.Min(p => (p - point).magnitude));
                        generic.generic_lbs_error_meters = Mathf.Max(generic.generic_lbs_error_meters, error);
                    }
                    generic.root_travel_meters = (bones["Root"].position - startRoot).magnitude;
                    if (generic.generic_lbs_error_meters > 1e-5f) throw new Exception("Sampled animation LBS differs from Blender by " + generic.generic_lbs_error_meters + " m");
                    if (Mathf.Abs(generic.root_travel_meters - reference.root_travel) > 1e-5f) throw new Exception("Root travel was lost or doubled");
                }
                generic.passed = true;
            }
            catch (Exception ex) { generic.error = ex.ToString(); Debug.LogError(ex); }
            results.Add(generic);

            AnimationClip humanClip = null;
            float sourceHumanScale = 0;
            AnimationValidation validation = null;
            string humanError = null;
            try
            {
                string modelPath = fixtureRoot + "/SyntheticMotionHumanoid/SyntheticMotionHumanoid.fbx";
                string clipPath = fixtureRoot + "/SyntheticMotionHumanoid/Animations/SelectedWave.fbx";
                CharacterImporter.Configure(modelPath);
                validation = AnimationImporter.Configure(clipPath);
                humanClip = AssetDatabase.LoadAllAssetsAtPath(clipPath).OfType<AnimationClip>().Single(c => !c.name.StartsWith("__preview__"));
                using (var preview = new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath)))
                    sourceHumanScale = preview.Root.GetComponent<Animator>().humanScale;
            }
            catch (Exception ex) { humanError = ex.ToString(); Debug.LogError(ex); }
            foreach (string name in new[] { "SyntheticT", "SyntheticA", "ShanePreserved" })
            {
                var result = new Result { name = "HumanoidClipTo" + name, validation = validation };
                try
                {
                    if (humanClip == null) throw new Exception(humanError ?? "Missing Human clip");
                    using (var preview = new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>($"{fixtureRoot}/{name}/{name}.fbx")))
                    {
                        var animator = preview.Root.GetComponent<Animator>();
                        animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                        animator.applyRootMotion = false; animator.Rebind();
                        var graph = PlayableGraph.Create("Local Character isolated clip acceptance");
                        try
                        {
                            graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                            var playable = AnimationClipPlayable.Create(graph, humanClip);
                            playable.SetApplyFootIK(false); playable.SetApplyPlayableIK(false);
                            var output = AnimationPlayableOutput.Create(graph, "Humanoid", animator);
                            output.SetSourcePlayable(playable); graph.Play();
                            playable.SetTime(0); graph.Evaluate(0);
                            var hand = animator.GetBoneTransform(HumanBodyBones.LeftHand);
                            var hips = animator.GetBoneTransform(HumanBodyBones.Hips);
                            var finger = animator.GetBoneTransform(HumanBodyBones.LeftIndexProximal);
                            var handBefore = hand.position - hips.position;
                            var fingerBefore = finger.localRotation;
                            playable.SetTime(humanClip.length / 2); graph.Evaluate(0);
                            result.hand_movement_meters = (hand.position - hips.position - handBefore).magnitude;
                            result.finger_rotation_degrees = Quaternion.Angle(fingerBefore, finger.localRotation);
                            if (result.hand_movement_meters < .01f || result.finger_rotation_degrees < 3)
                                throw new Exception("Retargeted clip did not animate both mapped hand and finger");
                            animator.applyRootMotion = true;
                            playable.SetTime(0); graph.Evaluate(0);
                            Vector3 rootBefore = preview.Root.transform.position;
                            for (int frame = 0; frame < 24; frame++) graph.Evaluate(1f / 24);
                            result.root_travel_meters = (preview.Root.transform.position - rootBefore).magnitude;
                            float expectedTravel = .3f * animator.humanScale / sourceHumanScale;
                            if (Mathf.Abs(result.root_travel_meters - expectedTravel) > 1e-4f)
                                throw new Exception("Retargeted root motion was lost or doubled: " + result.root_travel_meters);
                        }
                        finally { graph.Destroy(); }
                    }
                    result.passed = true;
                }
                catch (Exception ex) { result.error = ex.ToString(); Debug.LogError(ex); }
                results.Add(result);
            }
            return results;
        }
    }
}
