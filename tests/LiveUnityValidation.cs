// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Linq;
using LocalCharacter.Tests;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace LocalCharacter.Validation
{
    /// <summary>Install with the acceptance harness in the dedicated validation folder only.</summary>
    public static class LiveUnityValidation
    {
        const string Root = "Assets/LocalCharacterValidation";
        [Serializable] public class MaterialInfo { public string name, shader; public bool supported; }
        [Serializable] public class Report
        {
            public bool passed, user_scenes_preserved;
            public string render_pipeline, before_scenes, after_scenes;
            public UnityAcceptance.Results acceptance;
            public MaterialInfo[] imported_materials;
        }

        static string SceneSnapshot()
        {
            return string.Join("\n", Enumerable.Range(0,SceneManager.sceneCount).Select(i=>SceneManager.GetSceneAt(i))
                .Select(s=>$"{s.handle}|{s.path}|{s.isDirty}|{s.rootCount}|{s.handle==SceneManager.GetActiveScene().handle}"));
        }

        [MenuItem("Tools/Local Character/Validate Imported Fixtures")]
        public static void Validate()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode) throw new InvalidOperationException("Validation requires Edit Mode");
            var report=new Report { before_scenes=SceneSnapshot(), render_pipeline=GraphicsSettings.currentRenderPipeline==null?"Built-in":GraphicsSettings.currentRenderPipeline.GetType().FullName };
            try
            {
                report.acceptance=UnityAcceptance.Evaluate(Root+"/Fixtures");
                report.imported_materials=new[]{"SyntheticT","SyntheticA","ShanePreserved"}
                    .SelectMany(name=>AssetDatabase.LoadAssetAtPath<GameObject>($"{Root}/Fixtures/{name}/{name}.fbx").GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    .SelectMany(r=>r.sharedMaterials).Where(m=>m!=null).Distinct()
                    .Select(m=>new MaterialInfo { name=m.name,shader=m.shader==null?"missing":m.shader.name,supported=m.shader!=null&&m.shader.isSupported }).ToArray();
            }
            finally
            {
                report.after_scenes=SceneSnapshot();
                report.user_scenes_preserved=report.before_scenes==report.after_scenes;
                report.passed=report.user_scenes_preserved&&report.acceptance!=null&&report.acceptance.cases.All(c=>c.passed)&&report.acceptance.animations.All(c=>c.passed);
                File.WriteAllText(Root+"/live-validation.json",JsonUtility.ToJson(report,true));
                AssetDatabase.ImportAsset(Root+"/live-validation.json");
            }
            if(!report.passed)throw new InvalidOperationException("Live acceptance failed; inspect live-validation.json");
            Debug.Log("LOCAL_CHARACTER_LIVE_ACCEPTANCE PASSED; user scenes preserved");
        }

        [MenuItem("Tools/Local Character/Create Preview Scene")]
        public static void CreatePreview()
        {
            string path=Root+"/Scenes/LocalCharacterPreview.unity";
            if(File.Exists(path))throw new IOException("Preview already exists; existing scene will not be overwritten");
            if(!File.Exists(Root+"/live-validation.json"))throw new InvalidOperationException("Run fixture validation first");
            var report=JsonUtility.FromJson<Report>(File.ReadAllText(Root+"/live-validation.json"));
            if(!report.passed)throw new InvalidOperationException("Validation must pass before making the preview");
            Directory.CreateDirectory(Root+"/Scenes");Directory.CreateDirectory(Root+"/Materials");Directory.CreateDirectory(Root+"/Prefabs");
            AssetDatabase.Refresh();
            Scene original=SceneManager.GetActiveScene();
            Scene scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Additive);
            try
            {
                Shader shader=Shader.Find(GraphicsSettings.currentRenderPipeline==null?"Standard":"Universal Render Pipeline/Lit");
                if(shader==null)throw new InvalidOperationException("No supported basic preview shader");
                string[] names={"SyntheticT","SyntheticA","ShanePreserved"};
                for(int i=0;i<names.Length;i++)
                {
                    string name=names[i];
                    var source=AssetDatabase.LoadAssetAtPath<GameObject>($"{Root}/Fixtures/{name}/{name}.fbx");
                    var model=(GameObject)PrefabUtility.InstantiatePrefab(source,scene);
                    model.name=name;model.transform.position=new Vector3((i-1)*2,0,0);
                    foreach(var renderer in model.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    {
                        var materials=renderer.sharedMaterials;
                        for(int slot=0;slot<materials.Length;slot++)
                        {
                            var old=materials[slot];var material=new Material(shader);
                            material.name=$"{name}_{renderer.name}_{slot}_Preview";
                            material.SetColor(material.HasProperty("_BaseColor")?"_BaseColor":"_Color",i==0?new Color(.2f,.6f,.9f):i==1?new Color(.8f,.4f,.15f):Color.white);
                            if(old!=null)
                            {
                                Texture texture=old.HasProperty("_BaseMap")?old.GetTexture("_BaseMap"):old.HasProperty("_MainTex")?old.GetTexture("_MainTex"):null;
                                if(texture!=null)material.SetTexture(material.HasProperty("_BaseMap")?"_BaseMap":"_MainTex",texture);
                            }
                            AssetDatabase.CreateAsset(material,$"{Root}/Materials/{material.name}.mat");
                            materials[slot]=material;
                        }
                        renderer.sharedMaterials=materials;
                    }
                    PrefabUtility.SaveAsPrefabAsset(model,$"{Root}/Prefabs/{name}.prefab");
                }
                var ground=GameObject.CreatePrimitive(PrimitiveType.Plane);ground.name="Preview Ground";SceneManager.MoveGameObjectToScene(ground,scene);ground.transform.localScale=new Vector3(.8f,1,.6f);
                var groundMaterial=new Material(shader);groundMaterial.name="Preview Ground";groundMaterial.color=new Color(.15f,.18f,.21f);
                AssetDatabase.CreateAsset(groundMaterial,Root+"/Materials/PreviewGround.mat");ground.GetComponent<Renderer>().sharedMaterial=groundMaterial;
                var lightObject=new GameObject("Preview Key Light");SceneManager.MoveGameObjectToScene(lightObject,scene);var light=lightObject.AddComponent<Light>();light.type=LightType.Directional;light.intensity=1.4f;lightObject.transform.rotation=Quaternion.Euler(35,-30,0);
                var cameraObject=new GameObject("Preview Camera");SceneManager.MoveGameObjectToScene(cameraObject,scene);var camera=cameraObject.AddComponent<Camera>();cameraObject.transform.position=new Vector3(0,1.2f,-7);cameraObject.transform.LookAt(new Vector3(0,.85f,0));camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=new Color(.07f,.09f,.12f);camera.fieldOfView=36;camera.nearClipPlane=.05f;
                Isolate(scene);
                EditorSceneManager.SaveScene(scene,path);
                AssetDatabase.SaveAssets();
            }
            finally
            {
                if(original.IsValid()&&original.isLoaded)SceneManager.SetActiveScene(original);
                EditorSceneManager.CloseScene(scene,true);
            }
            Debug.Log("LOCAL_CHARACTER_PREVIEW_CREATED "+path+"; original active scene restored");
        }

        [MenuItem("Tools/Local Character/Isolate Preview Rendering")]
        public static void IsolatePreview()
        {
            var scene=SceneManager.GetSceneByPath(Root+"/Scenes/LocalCharacterPreview.unity");
            if(!scene.IsValid()||!scene.isLoaded)throw new InvalidOperationException("Open the generated preview additively first");
            Isolate(scene);
            EditorSceneManager.SaveScene(scene,scene.path);
            Debug.Log("LOCAL_CHARACTER_PREVIEW_ISOLATED; other scenes and layer definitions unchanged");
        }

        static void Isolate(Scene scene)
        {
            var used=Enumerable.Range(0,SceneManager.sceneCount).Select(i=>SceneManager.GetSceneAt(i)).Where(s=>s!=scene)
                .SelectMany(s=>s.GetRootGameObjects()).SelectMany(r=>r.GetComponentsInChildren<Renderer>(true))
                .Select(r=>r.gameObject.layer).ToHashSet();
            int layer=Enumerable.Range(8,24).Reverse().Where(index=>!used.Contains(index)).DefaultIfEmpty(-1).First();
            if(layer<0)throw new InvalidOperationException("No unused render layer is available for isolation");
            foreach(var root in scene.GetRootGameObjects())
            {
                foreach(var transform in root.GetComponentsInChildren<Transform>(true))transform.gameObject.layer=layer;
                foreach(var light in root.GetComponentsInChildren<Light>(true))light.cullingMask=1<<layer;
                foreach(var camera in root.GetComponentsInChildren<Camera>(true))
                {
                    camera.cullingMask=1<<layer;
                    camera.transform.position=new Vector3(0,1.2f,7);
                    camera.transform.LookAt(new Vector3(0,.85f,0));
                }
            }
        }
    }
}
