// SPDX-License-Identifier: MIT
using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LocalCharacter.Editor
{
    /// <summary>A disposable model instance isolated from the user's open scenes.</summary>
    public sealed class ModelPreview : IDisposable
    {
        Scene scene;
        public GameObject Root { get; private set; }
        public ModelPreview(GameObject model)
        {
            if (model == null) throw new ArgumentNullException(nameof(model));
            scene = EditorSceneManager.NewPreviewScene();
            try
            {
                Root = PrefabUtility.InstantiatePrefab(model, scene) as GameObject;
                if (Root == null) throw new InvalidOperationException("Cannot instantiate model in preview scene");
                Root.name = model.name;
                Root.hideFlags = HideFlags.HideAndDontSave;
            }
            catch { EditorSceneManager.ClosePreviewScene(scene); throw; }
        }
        public void Dispose()
        {
            if (Root != null) UnityEngine.Object.DestroyImmediate(Root);
            Root = null;
            if (scene.IsValid()) EditorSceneManager.ClosePreviewScene(scene);
        }
    }
}
