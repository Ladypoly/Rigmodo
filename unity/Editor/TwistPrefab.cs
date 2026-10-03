// SPDX-License-Identifier: MIT
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Editor
{
    public static class TwistPrefab
    {
        [MenuItem("Assets/Local Character/Create Humanoid Playback Prefab with Twists")]
        public static void CreateSelected()
        {
            string path=AssetDatabase.GetAssetPath(Selection.activeObject);
            try
            {
                var manifest=CharacterImporter.ReadManifest(path);
                if(manifest.profile!="HUMANOID"||manifest.twists==null||manifest.twists.Length!=2)throw new InvalidDataException("Select a configured Humanoid model exported with the optional two-helper twist module");
                var source=AssetDatabase.LoadAssetAtPath<GameObject>(path);
                var animator=source.GetComponent<Animator>();
                if(animator==null||animator.avatar==null||!animator.avatar.isHuman||!animator.avatar.isValid)throw new InvalidDataException("Configure the character export first");
                using(var preview=new ModelPreview(source))
                {
                    var copy=preview.Root;
                    copy.name=source.name;copy.hideFlags=HideFlags.None;var component=copy.AddComponent<LocalCharacterTwists>();component.BindRestPose();
                    foreach(var chain in component.chains)
                        foreach(var specification in manifest.twists)if(chain.helper.name==specification.helper)chain.fraction=specification.fraction;
                    string output=AssetDatabase.GenerateUniqueAssetPath(Path.ChangeExtension(path,null)+"-playback.prefab");
                    Selection.activeObject=PrefabUtility.SaveAsPrefabAsset(copy,output);
                }
            }
            catch(Exception error){Debug.LogError("Local Character: "+error.Message);}
        }
    }
}
