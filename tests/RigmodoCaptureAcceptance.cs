using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.Playables;
using UnityEngine.Animations;

public static class RigmodoCaptureAcceptance
{
    [Serializable] public class Report
    {
        public bool passed, genericPlayback, humanoidAvatar, humanoidPlayback, loopFlag, scenePreserved;
        public float genericFootMovement, humanoidFootMovement, genericLoopError, clipSeconds;
        public string error;
    }
    public static void Run()
    {
        var report = new Report(); var active = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        try
        {
            var path = "Assets/RigmodoCaptureWalk.fbx";
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            var importer = (ModelImporter)AssetImporter.GetAtPath(path);
            importer.importAnimation = true; importer.animationType = ModelImporterAnimationType.Generic;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            var settings = importer.defaultClipAnimations;
            foreach(var item in settings) { item.loopTime = true; item.loopPose = false; }
            importer.clipAnimations = settings; importer.SaveAndReimport();
            var generic = Sample(path, false); report.genericFootMovement=generic.Item1; report.genericLoopError=generic.Item2; report.clipSeconds=generic.Item3;
            report.genericPlayback = generic.Item1 > .01f && generic.Item2 < .005f;
            importer.animationType=ModelImporterAnimationType.Human; importer.SaveAndReimport();
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(path);
            var avatar=AssetDatabase.LoadAllAssetsAtPath(path).OfType<Avatar>().FirstOrDefault();
            report.humanoidAvatar=avatar && avatar.isValid && avatar.isHuman;
            if(!report.humanoidAvatar)throw new Exception("Unity did not create a valid humanoid Avatar");
            var human=Sample(path,true); report.humanoidFootMovement=human.Item1; report.humanoidPlayback=human.Item1>.01f;
            var clip=AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().First(c=>!c.name.StartsWith("__"));
            report.loopFlag=AnimationUtility.GetAnimationClipSettings(clip).loopTime;
            report.scenePreserved=UnityEngine.SceneManagement.SceneManager.GetActiveScene()==active;
            report.passed=report.genericPlayback && report.humanoidAvatar && report.humanoidPlayback && report.loopFlag && report.scenePreserved;
            if(!report.passed)throw new Exception("Captured clip failed playback/loop assertions");
        }
        catch(Exception exception) { report.error=exception.ToString(); report.passed=false; }
        File.WriteAllText(Path.Combine(Application.dataPath,"../rigmodo-unity-result.json"),JsonUtility.ToJson(report,true));
        Debug.Log("RIGMODO_UNITY_CAPTURE "+JsonUtility.ToJson(report)); EditorApplication.Exit(report.passed?0:1);
    }
    static Tuple<float,float,float> Sample(string path,bool human)
    {
        var scene=EditorSceneManager.NewPreviewScene(); GameObject root=null; PlayableGraph graph=default;
        try
        {
            root=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(path),scene);
            var animator=root.GetComponent<Animator>() ?? root.AddComponent<Animator>(); animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;
            var clip=AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().First(c=>!c.name.StartsWith("__"));
            Transform foot=human?animator.GetBoneTransform(HumanBodyBones.LeftFoot):root.GetComponentsInChildren<Transform>().First(t=>t.name=="LeftFoot");
            graph=PlayableGraph.Create("Rigmodo acceptance"); graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            var playable=AnimationClipPlayable.Create(graph,clip); playable.SetApplyFootIK(false);
            var output=AnimationPlayableOutput.Create(graph,"Capture",animator);output.SetSourcePlayable(playable);graph.Play();
            playable.SetTime(0);graph.Evaluate(0);var start=foot.position;
            playable.SetTime(clip.length*.4);graph.Evaluate(0);var middle=foot.position;
            playable.SetTime(clip.length);graph.Evaluate(0);var end=foot.position;
            return Tuple.Create(Vector3.Distance(start,middle),Vector3.Distance(start,end),clip.length);
        }
        finally { if(graph.IsValid())graph.Destroy(); if(root)UnityEngine.Object.DestroyImmediate(root); EditorSceneManager.ClosePreviewScene(scene); }
    }
}
