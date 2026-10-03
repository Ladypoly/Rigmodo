// SPDX-License-Identifier: MIT
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Tests
{
    public static class UnityAcceptance
    {
        [Serializable] public class Result
        {
            public string name, error;
            public bool passed, bind_preserved, vertices_preserved;
            public CharacterValidation validation;
            public float max_bind_delta;
            public float generic_lbs_error_meters, humanoid_hand_movement_meters;
            public bool humanoid_pose_applied;
        }
        [Serializable] public class Results { public string unity_version; public List<Result> cases = new List<Result>(); }
        public static void Run()
        {
            if (!Application.isBatchMode) throw new InvalidOperationException("Run is a batch entry point; use Evaluate for the live Editor");
            var results = Evaluate("Assets/Fixtures");
            string output = Path.Combine(Directory.GetParent(Application.dataPath).FullName,"unity-results.json");
            File.WriteAllText(output,JsonUtility.ToJson(results,true));
            Debug.Log("LOCAL_CHARACTER_UNITY_ACCEPTANCE " + output);
            EditorApplication.Exit(results.cases.All(c=>c.passed)?0:1);
        }

        public static Results Evaluate(string fixtureRoot)
        {
            var results = new Results { unity_version = Application.unityVersion };
            foreach (string name in new[] { "SyntheticT", "SyntheticA", "ShanePreserved" })
            {
                var result = new Result { name = name };
                try
                {
                    string path = $"{fixtureRoot.TrimEnd('/')}/{name}/{name}.fbx";
                    var importer = (ModelImporter)AssetImporter.GetAtPath(path);
                    importer.animationType = ModelImporterAnimationType.Generic;
                    importer.optimizeGameObjects = false;
                    importer.SaveAndReimport();
                    if (name.StartsWith("Synthetic")) result.generic_lbs_error_meters=CompareGeneric(path);
                    var before = AssetDatabase.LoadAssetAtPath<GameObject>(path).GetComponentsInChildren<SkinnedMeshRenderer>(true);
                    var binds = before.ToDictionary(r => r.name, r => r.sharedMesh.bindposes);
                    var vertices = before.ToDictionary(r => r.name, r => r.sharedMesh.vertices);
                    result.validation = CharacterImporter.Configure(path);
                    var after = AssetDatabase.LoadAssetAtPath<GameObject>(path).GetComponentsInChildren<SkinnedMeshRenderer>(true);
                    float maxDelta = 0;
                    bool sameVertices = true;
                    foreach (var renderer in after)
                    {
                        var previous = binds[renderer.name]; var current = renderer.sharedMesh.bindposes;
                        if (previous.Length != current.Length) throw new Exception("Bind count changed");
                        for (int i=0; i<previous.Length; i++)
                            for (int j=0; j<16; j++) maxDelta=Mathf.Max(maxDelta,Mathf.Abs(previous[i][j]-current[i][j]));
                        var v1 = vertices[renderer.name]; var v2 = renderer.sharedMesh.vertices;
                        sameVertices &= v1.Length == v2.Length && v1.Zip(v2,(a,b)=>(a-b).sqrMagnitude<1e-12f).All(v=>v);
                    }
                    result.max_bind_delta = maxDelta;
                    result.bind_preserved = maxDelta < 1e-5f;
                    result.vertices_preserved = sameVertices;
                    if (!result.bind_preserved || !sameVertices) throw new Exception("Humanoid calibration changed bind matrices or vertex coordinates");
                    int expectedShapes = name == "ShanePreserved" ? 3 : 1;
                    if (result.validation.blendshapes != expectedShapes) throw new Exception("Blendshape count mismatch");
                    if (name.StartsWith("Synthetic"))
                    {
                        float expectedHeight = name == "SyntheticT" ? 1.75f : 1.4f;
                        if (Mathf.Abs(result.validation.height_meters-expectedHeight)>.08f) throw new Exception("Meter scale/orientation mismatch: " + result.validation.height_meters);
                    }
                    using (var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(path)))
                    {
                        var instance=preview.Root;
                        var animator=instance.GetComponent<Animator>();
                        if (animator==null || animator.avatar==null) throw new Exception("No configured Animator/Avatar");
                        Transform hand=animator.GetBoneTransform(HumanBodyBones.LeftHand);
                        var beforeHand=hand.position;
                        using (var handler=new HumanPoseHandler(animator.avatar,instance.transform))
                        {
                            var pose=new HumanPose();handler.GetHumanPose(ref pose);
                            int muscle=Array.IndexOf(HumanTrait.MuscleName,"Left Arm Down-Up");
                            if (muscle<0) throw new Exception("Expected arm muscle is unavailable");
                            pose.muscles[muscle]=.6f;handler.SetHumanPose(ref pose);
                            result.humanoid_hand_movement_meters=(hand.position-beforeHand).magnitude;
                            result.humanoid_pose_applied=result.humanoid_hand_movement_meters>.01f;
                            if (!result.humanoid_pose_applied) throw new Exception("Humanoid pose did not move the mapped hand");
                        }
                    }
                    result.passed = true;
                }
                catch (Exception ex) { result.error = ex.ToString(); Debug.LogError(ex); }
                results.cases.Add(result);
            }
            return results;
        }

        static float CompareGeneric(string path)
        {
            string reference=Path.Combine(Path.GetDirectoryName(path),"generic-lbs-reference-flat.json");
            var data=JsonUtility.FromJson<FlatReference>(File.ReadAllText(reference));
            using (var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(path)))
            {
                var clone=preview.Root;
                var bones=clone.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t.name);
                Vector3 hips=bones["Hips"].position;
                Vector3 up=(bones["Head"].position-hips).normalized;
                Vector3 left=(bones["LeftArm"].position-bones["RightArm"].position).normalized;
                // FBX import reflects Blender's right-handed frame into Unity's left-handed frame.
                // A cross product is a pseudovector: both its parity and angle sign must convert.
                Vector3 forward=-Vector3.Cross(left,up).normalized;
                var arm=bones["LeftForeArm"];
                arm.rotation=Quaternion.AngleAxis(-data.angle,forward)*arm.rotation;
                var actual=new List<Vector3>();
                foreach (var renderer in clone.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    var mesh=new Mesh();
                    try
                    {
                        renderer.BakeMesh(mesh);
                        foreach(var vertex in mesh.vertices)
                        {
                            var delta=renderer.transform.TransformPoint(vertex)-hips;
                            actual.Add(new Vector3(Vector3.Dot(delta,left),Vector3.Dot(delta,forward),Vector3.Dot(delta,up)));
                        }
                    }
                    finally { UnityEngine.Object.DestroyImmediate(mesh); }
                }
                float error=0;
                File.WriteAllText(Path.Combine(Path.GetDirectoryName(path),"generic-lbs-actual.json"),JsonUtility.ToJson(new FlatReference { angle=data.angle, points=actual.ToArray() }));
                foreach(var point in actual) error=Mathf.Max(error,data.points.Min(p=>(p-point).magnitude));
                foreach(var point in data.points) error=Mathf.Max(error,actual.Min(p=>(p-point).magnitude));
                if(error>1e-5f) throw new Exception("Generic LBS differs from Blender by " + error + " m");
                return error;
            }
        }
        [Serializable] public class FlatReference { public float angle; public Vector3[] points; }
    }
}
