// Diagnostic against exported source float weights, in an isolated project only.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Tests
{
    public static class WeightPrecisionAcceptance
    {
        [Serializable] public class Vertex {public Vector3 position;public string[] bones;public float[] weights;}
        [Serializable] public class MeshReference {public string name;public Vertex[] vertices;}
        [Serializable] public class Reference {public MeshReference[] meshes;}
        [Serializable] public class Result {public string mesh;public float maximum_weight_error,maximum_weight_sum_error,maximum_bind_position_error;public int compared;}
        [Serializable] public class Report {public Result[] results;}
        public static void Run()
        {
            var results=new List<Result>();
            string directory="Assets/Fixtures/ActualGeneric";
            var reference=JsonUtility.FromJson<Reference>(File.ReadAllText(directory+"/weight-reference.json"));
            using(var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(directory+"/ActualGeneric.fbx")))
            {
                var bones=preview.Root.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t.name);
                Vector3 hips=bones["Hips"].position,up=(bones["Head"].position-hips).normalized,left=(bones["LeftArm"].position-bones["RightArm"].position).normalized;
                Vector3 forward=-Vector3.Cross(left,up).normalized;
                foreach(var renderer in preview.Root.GetComponentsInChildren<SkinnedMeshRenderer>())
                {
                    var result=new Result{mesh=renderer.name};results.Add(result);
                    var entries=reference.meshes.SelectMany(m=>m.vertices).ToArray();
                    var vertices=renderer.sharedMesh.vertices;var weights=renderer.sharedMesh.boneWeights;
                    for(int i=0;i<vertices.Length;i++)
                    {
                        Vector3 delta=renderer.transform.TransformPoint(vertices[i])-hips;
                        Vector3 point=new Vector3(Vector3.Dot(delta,left),Vector3.Dot(delta,forward),Vector3.Dot(delta,up));
                        var row=weights[i];var map=new Dictionary<string,float>();
                        int[] indices={row.boneIndex0,row.boneIndex1,row.boneIndex2,row.boneIndex3};float[] values={row.weight0,row.weight1,row.weight2,row.weight3};
                        for(int j=0;j<4;j++)if(values[j]>0)map[renderer.bones[indices[j]].name]=values[j];
                        var nearby=entries.Where(v=>(v.position-point).sqrMagnitude<1e-12f).ToArray();
                        if(nearby.Length==0)nearby=new[]{entries.OrderBy(v=>(v.position-point).sqrMagnitude).First()};
                        var match=nearby.OrderBy(v=>v.bones.Select((bone,j)=>Mathf.Abs(v.weights[j]-(map.TryGetValue(bone,out float value)?value:0))).Sum()).First();
                        result.maximum_bind_position_error=Mathf.Max(result.maximum_bind_position_error,(match.position-point).magnitude);
                        for(int j=0;j<match.bones.Length;j++)result.maximum_weight_error=Mathf.Max(result.maximum_weight_error,Mathf.Abs(match.weights[j]-(map.TryGetValue(match.bones[j],out float value)?value:0)));
                        result.maximum_weight_sum_error=Mathf.Max(result.maximum_weight_sum_error,Mathf.Abs(values.Sum()-1));result.compared++;
                    }
                }
            }
            File.WriteAllText("weight-precision.json",JsonUtility.ToJson(new Report{results=results.ToArray()},true));EditorApplication.Exit(0);
        }
    }
}
