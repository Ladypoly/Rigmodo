// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Linq;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;
using UnityEngine.SceneManagement;
namespace LocalCharacter.Tests
{
    public static class TransitionAcceptance
    {
        [Serializable] public class Result {public bool passed,scene_preserved,prefab_saved;public float maximum_hand_step_m,maximum_root_step_m,maximum_helper_step_degrees;}
        static AnimationClip Clip(string name)
        {
            string model="Assets/Fixtures/"+name+"/"+name+".fbx";CharacterImporter.Configure(model);
            var manifest=CharacterImporter.ReadManifest(model);string path="Assets/Fixtures/"+name+"/"+manifest.clips.Single().file;
            var report=AnimationImporter.Configure(path);
            return report.editable_clip_asset!=null?AssetDatabase.LoadAssetAtPath<AnimationClip>(report.editable_clip_asset):AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().Single(c=>!c.name.StartsWith("__preview__"));
        }
        public static void Run()
        {
            if(!Application.isBatchMode)throw new Exception("Use an isolated batch project");
            var result=new Result();int count=SceneManager.sceneCount;var active=SceneManager.GetActiveScene();bool dirty=active.isDirty;int roots=active.rootCount;
            try
            {
                var first=Clip("CardboardHUMANOID");var second=Clip("TurnHUMANOIDTrue");
                string path="Assets/Fixtures/FreshInstalledHUMANOID/FreshInstalledHUMANOID.fbx";CharacterImporter.Configure(path);
                var model=AssetDatabase.LoadAssetAtPath<GameObject>(path);Selection.activeObject=model;TwistPrefab.CreateSelected();
                var prefab=Selection.activeObject as GameObject;
                if(prefab==null||!AssetDatabase.GetAssetPath(prefab).EndsWith(".prefab"))throw new Exception("Playback prefab was not saved");
                var saved=prefab.GetComponent<LocalCharacterTwists>();
                if(saved==null||saved.chains.Length!=2||saved.chains.Any(c=>c.helper==null||c.source==null))throw new Exception("Saved prefab has missing twist references");
                result.prefab_saved=true;
                using(var preview=new ModelPreview(model))
                {
                    var target=preview.Root;var animator=target.GetComponent<Animator>();animator.applyRootMotion=true;animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;animator.Rebind();
                    var twists=target.AddComponent<LocalCharacterTwists>();twists.BindRestPose();
                    var graph=PlayableGraph.Create("External Humanoid transition test");
                    try
                    {
                        graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);var mixer=AnimationMixerPlayable.Create(graph,2);
                        var a=AnimationClipPlayable.Create(graph,first);var b=AnimationClipPlayable.Create(graph,second);
                        a.SetApplyFootIK(false);b.SetApplyFootIK(false);graph.Connect(a,0,mixer,0);graph.Connect(b,0,mixer,1);
                        var output=AnimationPlayableOutput.Create(graph,"Body",animator);output.SetSourcePlayable(mixer);mixer.SetInputWeight(0,1);graph.Play();graph.Evaluate(0);twists.Evaluate();
                        var hand=animator.GetBoneTransform(HumanBodyBones.LeftHand);Vector3 previousHand=hand.position,previousRoot=target.transform.position;
                        var previous=twists.chains.Select(c=>c.helper.localRotation).ToArray();
                        for(int frame=0;frame<48;frame++)
                        {
                            float weight=Mathf.Clamp01((frame-12)/24f);mixer.SetInputWeight(0,1-weight);mixer.SetInputWeight(1,weight);graph.Evaluate(1f/24);twists.Evaluate();
                            result.maximum_hand_step_m=Mathf.Max(result.maximum_hand_step_m,(hand.position-previousHand).magnitude);
                            result.maximum_root_step_m=Mathf.Max(result.maximum_root_step_m,(target.transform.position-previousRoot).magnitude);
                            for(int i=0;i<previous.Length;i++){result.maximum_helper_step_degrees=Mathf.Max(result.maximum_helper_step_degrees,Quaternion.Angle(previous[i],twists.chains[i].helper.localRotation));previous[i]=twists.chains[i].helper.localRotation;}
                            previousHand=hand.position;previousRoot=target.transform.position;
                        }
                        if(result.maximum_hand_step_m>.2f||result.maximum_root_step_m>.3f||result.maximum_helper_step_degrees>20)throw new Exception("Transition discontinuity exceeds diagnostic bounds");
                    }
                    finally{graph.Destroy();}
                }
                result.scene_preserved=count==SceneManager.sceneCount&&active==SceneManager.GetActiveScene()&&dirty==active.isDirty&&roots==active.rootCount;
                if(!result.scene_preserved)throw new Exception("Preview/prefab creation changed user scene state");
                result.passed=true;File.WriteAllText("transition-results.json",JsonUtility.ToJson(result,true));EditorApplication.Exit(0);
            }
            catch(Exception error){Debug.LogError(error);File.WriteAllText("transition-results.json",JsonUtility.ToJson(result,true));EditorApplication.Exit(1);}
        }
    }
}
