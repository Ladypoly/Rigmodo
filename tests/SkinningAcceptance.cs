// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LocalCharacter.Tests
{
    public static class SkinningAcceptance
    {
        [Serializable] public class WeightVertex { public Vector3 point; public string[] names; public float[] weights; }
        [Serializable] public class WeightDump { public WeightVertex[] vertices; }
        [Serializable] public class Result
        {
            public bool passed, user_scenes_preserved, vertices_preserved, binds_preserved;
            public string unity_version, error;
            public float generic_lbs_error_meters;
            public float initial_min_bone_weight, configured_min_bone_weight;
            public float minimum_full_api_weight=1;
            public float reloaded_min_bone_weight;
            public CharacterValidation avatar;
        }
        static string SceneSnapshot() => string.Join("\n", Enumerable.Range(0,SceneManager.sceneCount)
            .Select(i=>SceneManager.GetSceneAt(i)).Select(s=>$"{s.handle}|{s.path}|{s.isDirty}|{s.rootCount}|{s.handle==SceneManager.GetActiveScene().handle}"));

        [MenuItem("Tools/Local Character/Validate AI Skinning Transport")]
        public static void ValidateLive()
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode) throw new InvalidOperationException("Use Edit Mode");
            Evaluate("Assets/LocalCharacterValidation/Fixtures/ShaneAISkin/ShaneAISkin.fbx",
                "Assets/LocalCharacterValidation/ai-skin-validation.json");
        }
        public static void Run()
        {
            if(!Application.isBatchMode) throw new InvalidOperationException("Batch entry point only");
            try { Evaluate("Assets/Fixtures/ShaneAISkin/ShaneAISkin.fbx", "ai-skin-validation.json"); EditorApplication.Exit(0); }
            catch { EditorApplication.Exit(1); }
        }
        static void Evaluate(string path, string output)
        {
            var report=new Result { unity_version=Application.unityVersion };
            string before=SceneSnapshot();
            try
            {
                var importer=(ModelImporter)AssetImporter.GetAtPath(path);
                report.initial_min_bone_weight=importer.minBoneWeight;
                importer.animationType=ModelImporterAnimationType.Generic;
                importer.optimizeGameObjects=false;
                // Use the companion's explicit weight policy for the Generic
                // comparison, matching the independently prepared export copy.
                importer.skinWeights=ModelImporterSkinWeights.Custom;
                importer.maxBonesPerVertex=4; importer.minBoneWeight=.001f;
                report.configured_min_bone_weight=importer.minBoneWeight;
                importer.SaveAndReimport();
                AssetDatabase.ImportAsset(path,ImportAssetOptions.ForceUpdate|ImportAssetOptions.ForceSynchronousImport);
                report.reloaded_min_bone_weight=((ModelImporter)AssetImporter.GetAtPath(path)).minBoneWeight;
                using(var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(path)))
                {
                    var transforms=preview.Root.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t.name);
                    var hips=transforms["Hips"].position;
                    var up=(transforms["Head"].position-hips).normalized;
                    var left=(transforms["LeftArm"].position-transforms["RightArm"].position).normalized;
                    var forward=-Vector3.Cross(left,up).normalized;
                    var dump=new List<WeightVertex>();
                    foreach(var renderer in preview.Root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    {
                        var allWeights=renderer.sharedMesh.GetAllBoneWeights();
                        foreach(var weight in allWeights) report.minimum_full_api_weight=Mathf.Min(report.minimum_full_api_weight,weight.weight);
                        var localVertices=renderer.sharedMesh.vertices; var weights=renderer.sharedMesh.boneWeights;
                        for(int i=0;i<localVertices.Length;i++)
                        {
                            var p=renderer.transform.TransformPoint(localVertices[i])-hips; var w=weights[i];
                            var ids=new[]{w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};
                            dump.Add(new WeightVertex { point=new Vector3(Vector3.Dot(p,left),Vector3.Dot(p,forward),Vector3.Dot(p,up)),
                                names=ids.Select(id=>renderer.bones[id].name).ToArray(),weights=new[]{w.weight0,w.weight1,w.weight2,w.weight3} });
                        }
                    }
                    File.WriteAllText(Path.Combine(Path.GetDirectoryName(path),"unity-weight-diagnostic.json"),JsonUtility.ToJson(new WeightDump { vertices=dump.ToArray() }));
                }
                report.generic_lbs_error_meters=UnityAcceptance.CompareGeneric(path);
                var renderers=AssetDatabase.LoadAssetAtPath<GameObject>(path).GetComponentsInChildren<SkinnedMeshRenderer>(true);
                var vertices=renderers.ToDictionary(r=>r.name,r=>r.sharedMesh.vertices);
                var binds=renderers.ToDictionary(r=>r.name,r=>r.sharedMesh.bindposes);
                report.avatar=CharacterImporter.Configure(path);
                var after=AssetDatabase.LoadAssetAtPath<GameObject>(path).GetComponentsInChildren<SkinnedMeshRenderer>(true);
                report.vertices_preserved=after.All(r=>vertices[r.name].SequenceEqual(r.sharedMesh.vertices));
                report.binds_preserved=after.All(r=>binds[r.name].SequenceEqual(r.sharedMesh.bindposes));
                if(!report.avatar.valid_avatar || !report.avatar.human_avatar || report.avatar.blendshapes!=3 ||
                   !report.vertices_preserved || !report.binds_preserved) throw new Exception("AI weighted FBX import/calibration failed");
            }
            catch(Exception ex) { report.error=ex.ToString(); }
            finally
            {
                report.user_scenes_preserved=before==SceneSnapshot();
                report.passed=report.error==null&&report.user_scenes_preserved;
                File.WriteAllText(output,JsonUtility.ToJson(report,true));
            }
            if(!report.passed) throw new InvalidOperationException("AI transport validation failed: "+report.error);
            Debug.Log("LOCAL_CHARACTER_AI_SKIN_TRANSPORT PASSED (not a skin-quality benchmark)");
        }
    }
}
