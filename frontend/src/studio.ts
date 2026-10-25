import * as THREE from "three";

export type Stage = {
  setPitch: (archetype: string, company?: string) => void;
  mount: (host: HTMLElement) => void;
  setSpeaker: (index: number | null, text?: string, speakerName?: string) => void;
  updateSpeech: (text: string) => void;
  intro: (onComplete?: () => void, onShotChange?: (shot: number) => void) => void;
  skipIntro: () => void;
  dispose: () => void;
};

export function createStage(initialHost: HTMLElement): Stage | null {
  try {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x061123);
    scene.fog = new THREE.Fog(0x0a1830, 26, 52);
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 70);
    // Widen only the seated game view to approximate the scene scale at 75% browser zoom.
    const seatedViewFov = 61;
    const seatPosition = new THREE.Vector3(0, 1.72, 6.65);
    const cameraLookDownSlope = Math.tan(THREE.MathUtils.degToRad(7));
    const tiltLookTargetDown = (target: THREE.Vector3) => {
      const horizontalDistance = Math.hypot(target.x - seatPosition.x, target.z - seatPosition.z);
      target.y -= cameraLookDownSlope * horizontalDistance;
      return target;
    };
    const seatTarget = tiltLookTargetDown(new THREE.Vector3(0, 1.9, -4.7));
    camera.position.copy(seatPosition);
    camera.lookAt(seatTarget);

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.12;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.domElement.className = "stage-canvas";
    renderer.domElement.setAttribute("aria-hidden", "true");

    const metal = new THREE.MeshStandardMaterial({ color: 0x798998, metalness: 0.56, roughness: 0.38, flatShading: true });
    const darkMetal = new THREE.MeshStandardMaterial({ color: 0x111b28, metalness: 0.48, roughness: 0.42, flatShading: true });
    const wallMaterial = new THREE.MeshStandardMaterial({ color: 0x081425, metalness: 0.12, roughness: 0.78, flatShading: true });
    const walnut = new THREE.MeshStandardMaterial({ color: 0x4b261b, metalness: 0.04, roughness: 0.46, flatShading: true });
    const doorInset = new THREE.MeshStandardMaterial({ color: 0x352018, metalness: 0.03, roughness: 0.58, flatShading: true });
    const whiteLeather = new THREE.MeshStandardMaterial({ color: 0xdde8ed, metalness: 0.04, roughness: 0.39, flatShading: true });
    const stone = new THREE.MeshStandardMaterial({ color: 0x42505d, metalness: 0.02, roughness: 0.94, flatShading: true });
    const stoneCourses = [0x384653, 0x4a5660, 0x59616a, 0x313d49].map((color) => new THREE.MeshStandardMaterial({ color, roughness: 0.96, flatShading: true }));
    const foliageMaterials = [0x32634b, 0x47724d, 0x214f43].map((color) => new THREE.MeshStandardMaterial({ color, roughness: 0.92, flatShading: true }));
    const woodCanvas = document.createElement("canvas");
    woodCanvas.width = 512;
    woodCanvas.height = 512;
    const woodContext = woodCanvas.getContext("2d")!;
    woodContext.fillStyle = "#24150f";
    woodContext.fillRect(0, 0, 512, 512);
    const plankColors = ["#593522", "#65402a", "#50301f", "#704832", "#5c3825"];
    for (let row = 0; row < 8; row++) {
      const y = row * 64;
      const offset = row % 2 ? 128 : 0;
      for (let start = -offset, segment = 0; start < 512; start += 256, segment++) {
        const color = plankColors[(row * 3 + segment) % plankColors.length];
        const plank = woodContext.createLinearGradient(0, y, 0, y + 64);
        plank.addColorStop(0, color);
        plank.addColorStop(0.48, ["#6f472f", "#7c5035", "#60402b"][((row + segment) % 3)]);
        plank.addColorStop(1, color);
        woodContext.fillStyle = plank;
        woodContext.fillRect(start + 3, y + 3, 250, 58);
        woodContext.strokeStyle = "rgba(30, 15, 10, .34)";
        woodContext.lineWidth = 2;
        woodContext.strokeRect(start + 3, y + 3, 250, 58);
        for (let grain = 0; grain < 7; grain++) {
          const grainY = y + 9 + grain * 7 + ((row + grain) % 3);
          woodContext.strokeStyle = grain % 2 ? "rgba(35, 18, 11, .16)" : "rgba(211, 159, 104, .11)";
          woodContext.lineWidth = 1;
          woodContext.beginPath();
          woodContext.moveTo(start + 10, grainY);
          woodContext.bezierCurveTo(start + 72, grainY - 3, start + 172, grainY + 3, start + 246, grainY - 1);
          woodContext.stroke();
        }
      }
    }
    const woodTexture = new THREE.CanvasTexture(woodCanvas);
    woodTexture.colorSpace = THREE.SRGBColorSpace;
    woodTexture.wrapS = THREE.RepeatWrapping;
    woodTexture.wrapT = THREE.RepeatWrapping;
    woodTexture.repeat.set(4, 3);
    const floorMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, map: woodTexture, metalness: 0.08, roughness: 0.62, flatShading: true });
    const stageMaterial = new THREE.MeshStandardMaterial({ color: 0xb8875f, map: woodTexture, metalness: 0.12, roughness: 0.48, flatShading: true });
    const gold = new THREE.MeshStandardMaterial({ color: 0xbc8d51, metalness: 0.68, roughness: 0.31, flatShading: true });
    const goldGlow = new THREE.MeshStandardMaterial({ color: 0xffd99a, emissive: 0xd58a37, emissiveIntensity: 1.15, metalness: 0.1, roughness: 0.42, flatShading: true });
    const limeGlow = new THREE.MeshStandardMaterial({ color: 0x62d9ff, emissive: 0x127cb8, emissiveIntensity: 1.3, metalness: 0.16, roughness: 0.34, flatShading: true });
    const glass = new THREE.MeshStandardMaterial({ color: 0x6fc8e9, emissive: 0x0b456c, emissiveIntensity: 0.28, metalness: 0.2, roughness: 0.18, transparent: true, opacity: 0.46, depthWrite: false, flatShading: true, side: THREE.DoubleSide });
    const pendantShade = new THREE.MeshStandardMaterial({ color: 0x123b68, metalness: 0.48, roughness: 0.3, flatShading: true });

    const box = (parent: THREE.Object3D, size: [number, number, number], position: [number, number, number], material: THREE.Material, cast = false) => {
      const object = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
      object.position.set(...position);
      object.castShadow = cast;
      object.receiveShadow = true;
      parent.add(object);
      return object;
    };

    scene.add(new THREE.HemisphereLight(0x79bce0, 0x192334, 1.8));
    const coolFill = new THREE.PointLight(0x3f9de0, 74, 28, 1.5);
    coolFill.position.set(0, 6.5, -6.8);
    scene.add(coolFill);
    const warmFill = new THREE.PointLight(0xffb765, 52, 18, 2);
    warmFill.position.set(-5.4, 4.8, 0.5);
    scene.add(warmFill);

    // A television pitch set: blue city glow, dark gloss floor, warm timber and a presentation runway.
    const hallHalfWidth = 3.8;
    const hallWidth = hallHalfWidth * 2;
    const rearWallHalfWidth = 14.5;
    const rearSideWidth = rearWallHalfWidth - hallHalfWidth;
    const rearSideCenter = (rearWallHalfWidth + hallHalfWidth) / 2;
    const addWoodDoorLeaf = (parent: THREE.Object3D, side: -1 | 1) => {
      const leafWidth = hallHalfWidth;
      const centerX = side * leafWidth / 2;
      box(parent, [leafWidth, 4.1, 0.16], [centerX, 2.08, 0], walnut, true);
      box(parent, [leafWidth - 0.86, 1.25, 0.045], [centerX, 3.12, 0.105], doorInset, true);
      box(parent, [leafWidth - 0.86, 1.0, 0.045], [centerX, 1.28, 0.105], doorInset, true);
      box(parent, [0.07, 4.04, 0.2], [side * 0.1, 2.08, 0.1], gold);
      box(parent, [0.07, 4.04, 0.2], [side * (leafWidth - 0.1), 2.08, 0.1], gold);
      box(parent, [leafWidth - 0.16, 0.07, 0.2], [centerX, 0.14, 0.1], gold);
      box(parent, [leafWidth - 0.16, 0.07, 0.2], [centerX, 4.02, 0.1], gold);
      box(parent, [0.08, 0.48, 0.18], [side * (leafWidth - 0.33), 2.08, 0.2], goldGlow);
    };
    box(scene, [48, 0.16, 50], [0, -0.16, -1], floorMaterial);
    box(scene, [rearSideWidth, 9, 0.55], [-rearSideCenter, 4.35, -11.55], wallMaterial);
    box(scene, [rearSideWidth, 9, 0.55], [rearSideCenter, 4.35, -11.55], wallMaterial);
    box(scene, [hallWidth, 2.3, 0.55], [0, 7.8, -11.55], wallMaterial);
    for (const side of [-1, 1]) {
      const wing = box(scene, [0.56, 8.5, 16], [side * 13.35, 4.2, -4], wallMaterial);
      wing.rotation.y = side * 0.17;
      const rearWing = box(scene, [0.56, 8.5, 18.2], [side * 13.35, 4.2, 13.6], wallMaterial);
      rearWing.rotation.y = side * 0.17;
      const stonePier = box(scene, [0.92, 7.9, 1.38], [side * 11.95, 3.95, -9.65], stone);
      stonePier.rotation.y = side * 0.04;
      for (let slat = 0; slat < 8; slat++) {
        const x = side * (10.95 + slat * 0.17);
        box(scene, [0.09, 6.65, 0.18], [x, 3.7, -8.3 + slat * 0.13], walnut);
      }
      box(scene, [0.08, 0.055, 16.2], [side * 12.88, 7.55, -4], limeGlow);
      box(scene, [0.08, 0.055, 18.2], [side * 12.88, 7.55, 13.6], limeGlow);
      box(scene, [0.12, 0.055, 17], [side * 11.96, 0.04, -3.7], limeGlow);
    }

    // Stone courses and warm sconces carry the reference set dressing around both wings.
    const stoneInstances = stoneCourses.map(() => [] as { x: number; y: number; z: number; rotationY: number }[]);
    for (const side of [-1, 1]) {
      for (let row = 0; row < 12; row++) {
        const y = 0.38 + row * 0.59;
        const offset = row % 2 ? 0.65 : 0;
        for (let course = 0; course < 25; course++) {
          const z = course < 10
            ? -10.1 + course * 1.42 + offset
            : 2.8 + (course - 10) * 1.42 + offset;
          stoneInstances[(row * 3 + course) % stoneCourses.length].push({
            x: side * 12.98,
            y,
            z,
            rotationY: side * ((row + course) % 2 ? 0.018 : -0.012),
          });
        }
      }
      for (const z of [-6.4, -1.1, 5.0, 11.0, 17.0]) {
        box(scene, [0.2, 0.52, 0.48], [side * 12.82, 4.25, z], walnut);
        box(scene, [0.12, 0.12, 0.24], [side * 12.68, 4.06, z], goldGlow);
        const sconce = new THREE.PointLight(0xffa65d, 18, 6, 1.8);
        sconce.position.set(side * 12.1, 4.25, z);
        scene.add(sconce);
      }
    }
    const stoneBlockGeometry = new THREE.BoxGeometry(0.28, 0.53, 1.32);
    const stoneTransform = new THREE.Object3D();
    stoneInstances.forEach((instances, materialIndex) => {
      const blocks = new THREE.InstancedMesh(stoneBlockGeometry, stoneCourses[materialIndex], instances.length);
      instances.forEach((instance, index) => {
        stoneTransform.position.set(instance.x, instance.y, instance.z);
        stoneTransform.rotation.y = instance.rotationY;
        stoneTransform.updateMatrix();
        blocks.setMatrixAt(index, stoneTransform.matrix);
      });
      blocks.castShadow = true;
      blocks.receiveShadow = true;
      blocks.instanceMatrix.needsUpdate = true;
      scene.add(blocks);
    });
    const addPlanter = (x: number, z: number) => {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.48, 0.34, 0.62, 10), walnut);
      pot.position.set(x, 0.31, z);
      pot.castShadow = true;
      scene.add(pot);
      const rim = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.48, 0.1, 10), gold);
      rim.position.set(x, 0.62, z);
      scene.add(rim);
      for (let leaf = 0; leaf < 7; leaf++) {
        const angle = leaf * Math.PI * 2 / 7;
        const size = 0.36 + (leaf % 3) * 0.08;
        const frond = new THREE.Mesh(new THREE.IcosahedronGeometry(size, 0), foliageMaterials[leaf % foliageMaterials.length]);
        frond.position.set(x + Math.cos(angle) * 0.3, 0.95 + (leaf % 3) * 0.2, z + Math.sin(angle) * 0.3);
        frond.scale.set(0.72, 1.25, 0.62);
        frond.rotation.z = Math.cos(angle) * 0.24;
        frond.rotation.x = Math.sin(angle) * 0.22;
        frond.castShadow = true;
        scene.add(frond);
      }
    };
    addPlanter(-10.9, -5.6);
    addPlanter(10.9, -5.6);

    const skylineCanvas = document.createElement("canvas");
    skylineCanvas.width = 1400;
    skylineCanvas.height = 520;
    const skylineContext = skylineCanvas.getContext("2d")!;
    const skylineGradient = skylineContext.createLinearGradient(0, 0, 0, 520);
    skylineGradient.addColorStop(0, "#06132b");
    skylineGradient.addColorStop(0.52, "#0c4171");
    skylineGradient.addColorStop(1, "#07192f");
    skylineContext.fillStyle = skylineGradient;
    skylineContext.fillRect(0, 0, 1400, 520);
    const horizon = skylineContext.createLinearGradient(0, 330, 0, 505);
    horizon.addColorStop(0, "rgba(47, 173, 255, .46)");
    horizon.addColorStop(1, "rgba(4, 19, 39, 0)");
    skylineContext.fillStyle = horizon;
    skylineContext.fillRect(0, 280, 1400, 240);
    for (let star = 0; star < 76; star++) {
      const x = (star * 83) % 1400;
      const y = 38 + (star * 47) % 230;
      skylineContext.fillStyle = `rgba(188, 230, 255, ${0.18 + (star % 5) * 0.08})`;
      skylineContext.fillRect(x, y, star % 3 === 0 ? 3 : 2, 2);
    }
    for (let building = 0; building < 26; building++) {
      const width = 36 + (building * 29) % 82;
      const height = 105 + (building * 61) % 230;
      const x = building * 57 - 14;
      const y = 485 - height;
      skylineContext.fillStyle = building % 3 === 0 ? "#07172c" : building % 3 === 1 ? "#0b233c" : "#102f4a";
      skylineContext.fillRect(x, y, width, height);
      skylineContext.fillStyle = "rgba(129, 210, 255, .42)";
      for (let wy = y + 16; wy < 476; wy += 19) {
        for (let wx = x + 10; wx < x + width - 7; wx += 15) {
          if ((wx + wy + building) % 4 !== 0) skylineContext.fillRect(wx, wy, 5, 5);
        }
      }
    }
    skylineContext.fillStyle = "rgba(73, 190, 255, .55)";
    skylineContext.fillRect(0, 486, 1400, 4);
    const skylineTexture = new THREE.CanvasTexture(skylineCanvas);
    skylineTexture.colorSpace = THREE.SRGBColorSpace;
    skylineTexture.needsUpdate = true;
    const skylineMaterial = new THREE.MeshBasicMaterial({ map: skylineTexture, toneMapped: false, side: THREE.DoubleSide });
    for (const x of [-rearSideCenter, rearSideCenter]) {
      const skyline = new THREE.Mesh(new THREE.PlaneGeometry(rearSideWidth, 8.85), skylineMaterial);
      skyline.position.set(x, 4.35, -10.9);
      scene.add(skyline);
    }

    // Complete the room behind the investor with a windowed studio wall and set lighting.
    box(scene, [29, 9, 0.55], [0, 4.35, 23.0], wallMaterial);
    const rearSkyline = new THREE.Mesh(new THREE.PlaneGeometry(29, 8.85), skylineMaterial);
    rearSkyline.position.set(0, 4.35, 22.7);
    scene.add(rearSkyline);
    box(scene, [5.0, 4.45, 0.18], [0, 2.22, 22.53], darkMetal);
    for (const side of [-1, 1]) {
      box(scene, [2.36, 4.12, 0.14], [side * 1.19, 2.08, 22.37], walnut, true);
      box(scene, [1.68, 1.24, 0.045], [side * 1.19, 3.0, 22.27], doorInset);
      box(scene, [1.68, 1.03, 0.045], [side * 1.19, 1.2, 22.27], doorInset);
      box(scene, [0.065, 3.98, 0.18], [side * 0.11, 2.08, 22.25], gold);
      box(scene, [0.07, 0.5, 0.18], [side * 0.15, 2.08, 22.25], goldGlow);
      box(scene, [0.12, 4.5, 0.22], [side * 2.58, 2.22, 22.33], walnut);
    }
    box(scene, [5.25, 0.14, 0.22], [0, 4.48, 22.33], walnut);
    box(scene, [5.25, 0.06, 0.12], [0, 4.34, 22.19], goldGlow);
    for (const side of [-1, 1]) {
      for (let post = 0; post < 5; post++) {
        const x = side * (3.45 + post * 2.55);
        box(scene, [0.2, 7.45, 0.3], [x, 4.0, 22.46], walnut, true);
        box(scene, [0.045, 7.15, 0.06], [x - side * 0.13, 4.0, 22.27], goldGlow);
      }
    }
    box(scene, [29, 0.2, 0.34], [0, 7.72, 22.45], walnut);
    box(scene, [29, 0.12, 0.3], [0, 0.62, 22.45], walnut);

    const rearBlueWash = new THREE.PointLight(0x3b94ca, 44, 28, 1.6);
    rearBlueWash.position.set(0, 6.4, 18.4);
    scene.add(rearBlueWash);
    for (const x of [-10.8, 10.8]) {
      const rearWarmWash = new THREE.PointLight(0xffa45e, 28, 15, 1.8);
      rearWarmWash.position.set(x, 5.2, 19.5);
      scene.add(rearWarmWash);
    }

    for (const side of [-1, 1]) {
      for (let post = 0; post < 6; post++) {
        const x = side * (4.3 + post * 1.8);
        box(scene, [0.2, 7.1, 0.3], [x, 3.95, -10.72], walnut, true);
        box(scene, [0.045, 6.8, 0.06], [x - side * 0.13, 3.95, -10.53], goldGlow);
      }
    }
    box(scene, [27.2, 0.2, 0.32], [0, 7.47, -10.72], walnut);
    box(scene, [27.2, 0.07, 0.14], [0, 0.36, -10.7], walnut);

    const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(29, 50), new THREE.MeshStandardMaterial({ color: 0x0b1727, metalness: 0.16, roughness: 0.8, flatShading: true, side: THREE.DoubleSide }));
    ceiling.rotation.x = -Math.PI / 2;
    ceiling.position.set(0, 8.25, -1.5);
    scene.add(ceiling);
    for (const z of [-8.6, -2.2, 3.0, 9.5, 15.0, 20.5]) {
      box(scene, [26, 0.12, 0.16], [0, 7.92, z], darkMetal);
      for (const x of [-7.3, 0, 7.3]) {
        box(scene, [0.07, 1.0, 0.07], [x, 7.38, z], metal);
        const shade = new THREE.Mesh(new THREE.ConeGeometry(0.68, 0.46, 12, 1, true), pendantShade);
        shade.position.set(x, 7.16, z);
        scene.add(shade);
        const pendant = new THREE.Mesh(new THREE.CylinderGeometry(0.44, 0.67, 0.24, 12), goldGlow);
        pendant.position.set(x, 6.85, z);
        scene.add(pendant);
        const pendantLight = new THREE.PointLight(0xffc981, 27, 8, 1.8);
        pendantLight.position.set(x, 6.55, z);
        scene.add(pendantLight);
      }
    }

    // A wide timber entrance lets the presenter enter from the backstage corridor.
    const archPoints: THREE.Vector3[] = [];
    for (let step = 0; step <= 40; step++) {
      const angle = Math.PI - step / 40 * Math.PI;
      archPoints.push(new THREE.Vector3(Math.cos(angle) * 7.5, 3.15 + Math.sin(angle) * 3.6, -10.83));
    }
    const arch = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(archPoints), 80, 0.07, 8), goldGlow);
    scene.add(arch);
    const innerArch = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(archPoints.map((point) => new THREE.Vector3(point.x * 0.92, point.y * 0.92, point.z + 0.07))), 80, 0.036, 8), limeGlow);
    scene.add(innerArch);
    box(scene, [hallWidth, 0.1, 0.26], [0, 4.35, -10.83], goldGlow);
    box(scene, [0.1, 4.4, 0.23], [-hallHalfWidth, 2.18, -10.82], goldGlow);
    box(scene, [0.1, 4.4, 0.23], [hallHalfWidth, 2.18, -10.82], goldGlow);
    const leftDoor = new THREE.Group();
    const rightDoor = new THREE.Group();
    leftDoor.position.set(-hallHalfWidth, 0, -10.65);
    rightDoor.position.set(hallHalfWidth, 0, -10.65);
    scene.add(leftDoor, rightDoor);
    addWoodDoorLeaf(leftDoor, 1);
    addWoodDoorLeaf(rightDoor, -1);

    // The backstage corridor leads to a second entrance behind the stage doors.
    const hallStartZ = -10.92;
    const hallEndZ = -18.92;
    const hallLength = hallStartZ - hallEndZ;
    const hallCenterZ = (hallStartZ + hallEndZ) / 2;
    const vestibuleCenterZ = -21.42;
    box(scene, [0.18, 5.45, hallLength], [-hallHalfWidth, 2.72, hallCenterZ], wallMaterial);
    box(scene, [0.18, 5.45, hallLength], [hallHalfWidth, 2.72, hallCenterZ], wallMaterial);
    box(scene, [hallWidth, 0.18, hallLength], [0, 5.38, hallCenterZ], darkMetal);
    box(scene, [hallWidth - 0.4, 0.04, hallLength - 0.15], [0, -0.045, hallCenterZ], stageMaterial);
    box(scene, [0.18, 5.45, 5], [-hallHalfWidth, 2.72, vestibuleCenterZ], wallMaterial);
    box(scene, [0.18, 5.45, 5], [hallHalfWidth, 2.72, vestibuleCenterZ], wallMaterial);
    box(scene, [hallWidth, 0.18, 5], [0, 5.38, vestibuleCenterZ], darkMetal);
    box(scene, [hallWidth - 0.4, 0.16, 5], [0, -0.16, vestibuleCenterZ], floorMaterial);
    for (const side of [-1, 1]) {
      box(scene, [0.055, 0.045, hallLength - 0.3], [side * (hallHalfWidth - 0.32), 0.07, hallCenterZ], limeGlow);
      for (const z of [-12.0, -14.5, -17.0]) {
        box(scene, [0.11, 5.25, 0.13], [side * (hallHalfWidth - 0.18), 2.68, z], walnut);
        box(scene, [0.06, 0.035, 0.16], [side * (hallHalfWidth - 0.28), 4.95, z], goldGlow);
      }
    }
    for (const z of [-12.4, -15.1, -17.6]) {
      const hallLight = new THREE.PointLight(0xffc981, 13, 5.2, 1.7);
      hallLight.position.set(0, 4.85, z);
      scene.add(hallLight);
    }

    const backstageWallZ = -19.03;
    const backstageSideWidth = rearSideWidth;
    const backstageSideCenter = rearSideCenter;
    box(scene, [backstageSideWidth, 5.45, 0.24], [-backstageSideCenter, 2.72, backstageWallZ], wallMaterial);
    box(scene, [backstageSideWidth, 5.45, 0.24], [backstageSideCenter, 2.72, backstageWallZ], wallMaterial);
    box(scene, [hallWidth, 1.3, 0.24], [0, 4.78, backstageWallZ], wallMaterial);
    box(scene, [hallWidth, 5.45, 0.22], [0, 2.72, -23.92], darkMetal);
    for (const x of [-hallHalfWidth, hallHalfWidth]) box(scene, [0.09, 4.08, 0.22], [x, 2.05, -18.88], goldGlow);
    box(scene, [hallWidth, 0.1, 0.22], [0, 4.12, -18.88], goldGlow);
    const hallLeftDoor = new THREE.Group();
    const hallRightDoor = new THREE.Group();
    hallLeftDoor.position.set(-hallHalfWidth, 0, -18.86);
    hallRightDoor.position.set(hallHalfWidth, 0, -18.86);
    scene.add(hallLeftDoor, hallRightDoor);
    addWoodDoorLeaf(hallLeftDoor, 1);
    addWoodDoorLeaf(hallRightDoor, -1);

    const signCanvas = document.createElement("canvas");
    signCanvas.width = 1024;
    signCanvas.height = 344;
    const signContext = signCanvas.getContext("2d")!;
    const signTexture = new THREE.CanvasTexture(signCanvas);
    signTexture.colorSpace = THREE.SRGBColorSpace;
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(6.3, 2.13), new THREE.MeshBasicMaterial({ map: signTexture, toneMapped: false }));
    sign.position.set(0, 5.6, -10.67);
    scene.add(sign);
    const drawSign = (company?: string) => {
      const context = signContext;
      const gradient = context.createLinearGradient(0, 0, 1024, 344);
      gradient.addColorStop(0, "#071a32");
      gradient.addColorStop(0.5, "#0b3b64");
      gradient.addColorStop(1, "#071a32");
      context.fillStyle = gradient;
      context.fillRect(0, 0, 1024, 344);
      context.strokeStyle = "#76d5fa";
      context.lineWidth = 3;
      context.strokeRect(18, 18, 988, 308);
      context.strokeStyle = "#d5a25c";
      context.lineWidth = 6;
      context.beginPath();
      context.moveTo(92, 85);
      context.lineTo(187, 85);
      context.moveTo(837, 85);
      context.lineTo(932, 85);
      context.stroke();
      context.textAlign = "center";
      context.fillStyle = "#9ee6ff";
      context.font = "700 30px Arial";
      context.fillText("THE", 512, 76);
      context.fillStyle = "#ffffff";
      context.font = "700 80px Arial";
      context.fillText("SHRIMP TANK", 512, 172);
      context.fillStyle = "#c9e8f5";
      context.font = "600 23px Arial";
      context.fillText(company ? company.toUpperCase() : "THE UNDERWRITING STUDIO", 512, 255, 790);
      signTexture.needsUpdate = true;
    };
    drawSign();

    // Layered blue presentation pad, slim runway, and warm brass edge at the investor side.
    box(scene, [3.2, 0.2, 4.8], [0, 0.06, -8.35], walnut, true);
    box(scene, [3.1, 0.06, 4.62], [0, 0.17, -8.35], stageMaterial, true);
    box(scene, [12.0, 0.38, 7.0], [0, 0.15, -4.45], stageMaterial, true);
    box(scene, [12.15, 0.08, 0.1], [0, 0.39, -0.9], goldGlow);
    for (const side of [-1, 1]) {
      box(scene, [0.085, 0.06, 6.95], [side * 6.0, 0.39, -4.45], limeGlow);
      box(scene, [0.05, 0.05, 4.68], [side * 1.58, 0.22, -8.35], limeGlow);
    }
    box(scene, [10.0, 0.19, 0.7], [0, 0.05, -0.42], darkMetal);
    box(scene, [9.75, 0.09, 0.68], [0, -0.02, 0.01], darkMetal);
    box(scene, [10.05, 0.055, 0.08], [0, 0.15, -0.08], goldGlow);
    const centerRing = new THREE.Mesh(new THREE.RingGeometry(0.75, 0.8, 8), new THREE.MeshBasicMaterial({ color: 0x6dd8ff, side: THREE.DoubleSide, transparent: true, opacity: 0.85 }));
    centerRing.rotation.x = -Math.PI / 2;
    centerRing.position.set(0, 0.395, -4.45);
    scene.add(centerRing);

    const spotlights: THREE.SpotLight[] = [];
    for (const [x, color, intensity] of [[-4.6, 0x6fbef0, 96], [0, 0xffd59a, 160], [4.6, 0x6fbef0, 96]] as [number, number, number][]) {
      const light = new THREE.SpotLight(color, intensity, 24, Math.PI / 7, 0.5, 1.7);
      light.position.set(x, 7.2, -4.25);
      light.target.position.set(x * 0.3, 0.25, -4.55);
      if (x === 0) {
        light.castShadow = true;
        light.shadow.mapSize.set(1024, 1024);
        light.shadow.bias = -0.001;
      }
      scene.add(light, light.target);
      spotlights.push(light);
      const beam = new THREE.Mesh(new THREE.ConeGeometry(2.05, 7.0, 28, 1, true), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.035, depthWrite: false, side: THREE.DoubleSide }));
      beam.position.set(x * 0.8, 3.7, -4.2);
      scene.add(beam);
    }

    type Actor = { group: THREE.Group; shell: THREE.MeshStandardMaterial; legs: THREE.Group[]; eyes: THREE.Group };
    const makeActor = (shellColor: number): Actor => {
      const group = new THREE.Group();
      const shell = new THREE.MeshStandardMaterial({ color: shellColor, roughness: 0.84, metalness: 0.02, flatShading: true });
      const underside = new THREE.MeshStandardMaterial({ color: new THREE.Color(shellColor).multiplyScalar(0.62), roughness: 0.92, flatShading: true });
      const black = new THREE.MeshStandardMaterial({ color: 0x171715, roughness: 0.35, flatShading: true });
      const shine = new THREE.MeshBasicMaterial({ color: 0xfff5da });
      const profile = [
        new THREE.Vector2(0.02, 0.02), new THREE.Vector2(0.2, 0.11), new THREE.Vector2(0.39, 0.44),
        new THREE.Vector2(0.56, 1.0), new THREE.Vector2(0.59, 1.53), new THREE.Vector2(0.48, 2.0),
        new THREE.Vector2(0.29, 2.48), new THREE.Vector2(0.11, 2.78), new THREE.Vector2(0.015, 2.88),
      ];
      const carapace = new THREE.Mesh(new THREE.LatheGeometry(profile, 7), shell);
      carapace.position.y = 0.16;
      carapace.castShadow = true;
      carapace.scale.z = 0.78;
      group.add(carapace);

      for (let segment = 0; segment < 4; segment++) {
        const y = 0.28 + segment * 0.34;
        const plate = new THREE.Mesh(new THREE.SphereGeometry(1, 6, 4), underside);
        plate.position.set(0, y, -0.23);
        plate.scale.set(0.31 - segment * 0.025, 0.2, 0.14);
        plate.castShadow = true;
        group.add(plate);
      }

      const eyes = new THREE.Group();
      eyes.position.set(0, 2.15, 0.015);
      const stalkMaterial = new THREE.MeshStandardMaterial({ color: shellColor, roughness: 0.85, flatShading: true });
      const addSegment = (parent: THREE.Object3D, start: THREE.Vector3, end: THREE.Vector3, radius: number, material: THREE.Material, facets = 5) => {
        const direction = end.clone().sub(start);
        const segment = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.7, radius, direction.length(), facets), material);
        segment.position.copy(start).add(end).multiplyScalar(0.5);
        segment.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
        segment.castShadow = true;
        parent.add(segment);
        return segment;
      };
      for (const side of [-1, 1]) {
        const root = new THREE.Vector3(side * 0.18, 0.07, 0.04);
        const tip = new THREE.Vector3(side * 0.45, 0.2, 0.08);
        addSegment(eyes, root, tip, 0.075, stalkMaterial, 5);
        const eye = new THREE.Mesh(new THREE.SphereGeometry(0.155, 7, 5), black);
        eye.position.copy(tip).add(new THREE.Vector3(side * 0.025, 0.02, 0.02));
        eye.castShadow = true;
        eyes.add(eye);
        const sparkle = new THREE.Mesh(new THREE.SphereGeometry(0.042, 5, 4), shine);
        sparkle.position.copy(eye.position).add(new THREE.Vector3(-side * 0.035, 0.045, 0.123));
        eyes.add(sparkle);
        const antennaBase = new THREE.Vector3(side * 0.09, 0.4, -0.02);
        const antennaTip = new THREE.Vector3(side * 0.36, 0.94, -0.07);
        addSegment(eyes, antennaBase, antennaTip, 0.025, stalkMaterial, 4);
      }
      group.add(eyes);

      const legs: THREE.Group[] = [];
      for (let pair = 0; pair < 3; pair++) {
        for (const side of [-1, 1]) {
          const leg = new THREE.Group();
          const y = 1.32 - pair * 0.42;
          leg.position.set(side * 0.32, y, 0.02);
          const knee = new THREE.Vector3(side * (0.58 + pair * 0.05), pair === 0 ? 0.13 : 0.02, 0.04 + pair * 0.035);
          const foot = new THREE.Vector3(side * (0.95 + pair * 0.08), -0.42 + pair * 0.12, 0.13 + pair * 0.08);
          addSegment(leg, new THREE.Vector3(0, 0, 0), knee, 0.078 - pair * 0.008, shell, 5);
          const joint = new THREE.Mesh(new THREE.IcosahedronGeometry(0.073, 0), shell);
          joint.position.copy(knee);
          leg.add(joint);
          addSegment(leg, knee, foot, 0.052 - pair * 0.005, shell, 5);
          group.add(leg);
          legs.push(leg);
        }
      }
      return { group, shell, legs, eyes };
    };

    const founder = makeActor(0xe5222b);
    founder.group.position.set(0, 0.4, -4.42);
    scene.add(founder.group);
    const sharkColors = [0xb71020, 0xe0372d, 0xa1131d];
    // The player occupies the center of the investor arc; the other sharks sit in curved white stations.
    // Stations occupy the same shallow semicircle as the player's center seat.
    const investorArcCenterZ = -0.6;
    const investorArcRadius = 7.5;
    // These are the sharks' chair-back positions along the same arc as the player's center seat.
    const sharkSeatPositions: [number, number][] = [-7.1, -4.0, 6.2].map((x) => [
      x,
      investorArcCenterZ + Math.sqrt(investorArcRadius ** 2 - x ** 2),
    ]);
    const sharks = sharkSeatPositions.map(([seatX, seatZ], index) => {
      const station = new THREE.Group();
      let angle = Math.atan2(-seatX, founder.group.position.z - seatZ);
      let chairOffset = new THREE.Vector3(0, 0, -0.62).applyAxisAngle(new THREE.Vector3(0, 1, 0), angle);
      station.position.set(seatX - chairOffset.x, 0, seatZ - chairOffset.z);
      angle = Math.atan2(-station.position.x, founder.group.position.z - station.position.z);
      chairOffset = new THREE.Vector3(0, 0, -0.62).applyAxisAngle(new THREE.Vector3(0, 1, 0), angle);
      station.position.set(seatX - chairOffset.x, 0, seatZ - chairOffset.z);
      station.rotation.y = angle;
      scene.add(station);
      box(station, [1.38, 0.7, 0.17], [0, 1.12, -0.62], whiteLeather, true);
      box(station, [1.42, 0.16, 0.82], [0, 0.73, -0.42], whiteLeather, true);
      const tableBase = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.46, 0.12, 12), darkMetal);
      tableBase.position.set(0, 0.12, 1.0);
      station.add(tableBase);
      const tablePedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.19, 0.78, 8), darkMetal);
      tablePedestal.position.set(0, 0.55, 1.0);
      station.add(tablePedestal);
      const tableTop = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.13, 16), walnut);
      tableTop.position.set(0, 0.99, 1.0);
      station.add(tableTop);
      const tableRim = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.8, 0.035, 16), gold);
      tableRim.position.set(0, 1.075, 1.0);
      station.add(tableRim);
      const actor = makeActor(sharkColors[index]);
      actor.group.position.set(0, 0.12, 0.09);
      actor.group.scale.setScalar(0.76);
      station.add(actor.group);
      const tablet = box(station, [0.52, 0.035, 0.34], [0, 1.075, 1.0], glass);
      tablet.rotation.x = 0.14;
      return actor;
    });

    // The player has the matching center chair and round investor table.
    box(scene, [1.38, 0.7, 0.17], [0, 1.12, investorArcCenterZ + investorArcRadius], whiteLeather, true);
    box(scene, [1.42, 0.16, 0.82], [0, 0.73, investorArcCenterZ + investorArcRadius - 0.22], whiteLeather, true);
    const playerTableZ = investorArcCenterZ + investorArcRadius - 1.7;
    const playerTableBase = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.46, 0.12, 12), darkMetal);
    playerTableBase.position.set(0, 0.12, playerTableZ);
    scene.add(playerTableBase);
    const playerTablePedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.19, 0.78, 8), darkMetal);
    playerTablePedestal.position.set(0, 0.55, playerTableZ);
    scene.add(playerTablePedestal);
    const playerTableTop = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.13, 16), walnut);
    playerTableTop.position.set(0, 0.99, playerTableZ);
    scene.add(playerTableTop);
    const playerTableRim = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.8, 0.035, 16), gold);
    playerTableRim.position.set(0, 1.075, playerTableZ);
    scene.add(playerTableRim);
    const deskScreen = box(scene, [0.52, 0.035, 0.34], [0, 1.075, playerTableZ], glass);
    deskScreen.rotation.x = 0.14;

    type SpeechBubble = { sprite: THREE.Sprite; context: CanvasRenderingContext2D; texture: THREE.CanvasTexture };
    const createBubble = (position: THREE.Vector3, scale: [number, number]): SpeechBubble => {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 300;
      const context = canvas.getContext("2d")!;
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false });
      const sprite = new THREE.Sprite(material);
      sprite.position.copy(position);
      sprite.scale.set(scale[0], scale[1], 1);
      sprite.renderOrder = 20;
      sprite.visible = false;
      scene.add(sprite);
      return { sprite, context, texture };
    };
    const drawBubble = (bubble: SpeechBubble, text: string, speakerName = "") => {
      const context = bubble.context;
      const words = (text.trim() || "…").split(/\s+/);
      const maxTextWidth = 510;
      const lineHeight = 39;
      const firstBaseline = speakerName ? 88 : 72;
      context.font = "600 27px Arial";
      const lines: string[] = [];
      let line = "";
      for (const word of words) {
        let remainder = word;
        while (remainder && context.measureText(remainder).width > maxTextWidth) {
          const characters = Array.from(remainder);
          let splitAt = characters.length;
          while (splitAt > 1 && context.measureText(characters.slice(0, splitAt).join("")).width > maxTextWidth) splitAt--;
          if (line) {
            lines.push(line);
            line = "";
          }
          lines.push(characters.slice(0, splitAt).join(""));
          remainder = characters.slice(splitAt).join("");
        }
        if (!remainder) continue;
        const candidate = line ? `${line} ${remainder}` : remainder;
        if (line && context.measureText(candidate).width > maxTextWidth) {
          lines.push(line);
          line = remainder;
        } else {
          line = candidate;
        }
      }
      if (line) lines.push(line);

      const visibleLines = lines.slice(-4);
      context.clearRect(0, 0, 640, 300);
      context.fillStyle = "rgba(0, 10, 24, .38)";
      context.beginPath();
      context.roundRect(34, 23, 572, 232, 26);
      context.moveTo(295, 245);
      context.lineTo(340, 245);
      context.lineTo(318, 291);
      context.closePath();
      context.fill();
      context.fillStyle = "#f3fbff";
      context.strokeStyle = "#146b9b";
      context.lineWidth = 8;
      context.lineJoin = "round";
      context.beginPath();
      context.roundRect(26, 14, 572, 232, 26);
      context.moveTo(286, 239);
      context.lineTo(330, 239);
      context.lineTo(307, 285);
      context.closePath();
      context.fill();
      context.stroke();
      context.fillStyle = "#092039";
      context.font = "600 27px Arial";
      context.textAlign = "left";
      if (speakerName) {
        context.fillStyle = "#146b9b";
        context.font = "700 23px Arial";
        context.fillText(`${speakerName}:`, 58, 58);
        context.fillStyle = "#092039";
        context.font = "600 27px Arial";
      }
      visibleLines.forEach((wrappedLine, index) => context.fillText(wrappedLine, 58, firstBaseline + index * lineHeight));
      bubble.texture.needsUpdate = true;
    };
    const actors = [founder, ...sharks];
    const speechBubbles = actors.map((actor, index) => {
      const point = new THREE.Vector3();
      const world = new THREE.Vector3();
      actor.group.getWorldPosition(world);
      if (index === 0) point.set(world.x, world.y + 3.55, world.z + 0.05);
      else {
        const offsetTowardCenter = world.x < 0 ? 1.15 : -1.15;
        point.set(world.x + offsetTowardCenter * 0.4, world.y + 3.15, world.z - 0.35);
      }
      return createBubble(point, index === 0 ? [4.6, 2.1] : [3.2, 1.5]);
    });
    const activeBubble: { current: SpeechBubble | null } = { current: null };
    let activeBubbleSpeaker = "";

    const actorLights = actors.map((actor, index) => {
      const light = new THREE.PointLight(index === 0 ? 0xffffce : 0xf8be92, 0, 5, 2);
      const world = new THREE.Vector3();
      actor.group.getWorldPosition(world);
      light.position.copy(world).add(new THREE.Vector3(0, 3.0, 0.7));
      scene.add(light);
      return light;
    });

    const dustPoints: THREE.Vector3[] = [];
    for (let index = 0; index < 90; index++) {
      const x = Math.sin(index * 16.17) * 8;
      const y = 1.3 + (index * 7 % 57) / 10;
      const z = -10 + (index * 13 % 90) / 10;
      dustPoints.push(new THREE.Vector3(x, y, z));
    }
    const dust = new THREE.Points(new THREE.BufferGeometry().setFromPoints(dustPoints), new THREE.PointsMaterial({ color: 0x9cdefa, size: 0.023, transparent: true, opacity: 0.35 }));
    scene.add(dust);
    let host = initialHost;
    let frame = 0;
    let introStart = 0;
    let introducing = false;
    let manualView = false;
    let dragging = false;
    let lastPointerX = 0;
    let lastPointerY = 0;
    let viewYaw = 0;
    let viewPitch = 0;
    let selectedSpeaker: number | null = null;
    let introCompleteCallback: (() => void) | null = null;
    let introShotCallback: ((shot: number) => void) | null = null;
    let activeIntroShot = -1;
    const introHallCamera = new THREE.Vector3(2.8, 2.35, -14.9);
    const introStageCamera = new THREE.Vector3(-1.1, 2.35, -13.25);
    const introSeatLookStart = new THREE.Vector3(0, 2.0, -10.7);
    const introDuration = 8000;
    const maxViewYaw = Math.PI * 0.46;
    const look = new THREE.Vector3();
    const normalLook = seatTarget.clone();
    const speakerLook = new THREE.Vector3();
    const direction = new THREE.Vector3();
    const finishIntro = () => {
      if (!introducing) return;
      introducing = false;
      founder.group.position.z = -4.42;
      leftDoor.rotation.y = 0;
      rightDoor.rotation.y = 0;
      hallLeftDoor.rotation.y = 0;
      hallRightDoor.rotation.y = 0;
      manualView = false;
      camera.position.copy(seatPosition);
      camera.fov = seatedViewFov;
      camera.updateProjectionMatrix();
      normalLook.copy(seatTarget);
      camera.lookAt(seatTarget);
      const onComplete = introCompleteCallback;
      introCompleteCallback = null;
      introShotCallback = null;
      activeIntroShot = -1;
      onComplete?.();
    };
    const resize = () => {
      const width = Math.max(1, host.clientWidth);
      const height = Math.max(1, host.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    const mount = (target: HTMLElement) => {
      if (host !== target) {
        observer.unobserve(host);
        host.classList.remove("has-webgl");
        host = target;
        host.appendChild(renderer.domElement);
        observer.observe(host);
      } else if (renderer.domElement.parentElement !== host) {
        host.appendChild(renderer.domElement);
      }
      host.classList.add("has-webgl");
      resize();
    };
    mount(initialHost);

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      if (introducing || (!host.classList.contains("game-stage") && !host.classList.contains("hero-scene"))) return;
      const target = event.target;
      if (target instanceof Element && target.closest("button, input, textarea, select, a, summary, label, [contenteditable='true']")) return;
      dragging = true;
      camera.getWorldDirection(direction);
      viewYaw = Math.atan2(direction.x, -direction.z);
      viewPitch = Math.asin(THREE.MathUtils.clamp(direction.y, -1, 1));
      lastPointerX = event.clientX;
      lastPointerY = event.clientY;
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!dragging) return;
      const deltaX = event.clientX - lastPointerX;
      const deltaY = event.clientY - lastPointerY;
      if (deltaX || deltaY) {
        manualView = true;
        event.preventDefault();
      }
      viewYaw = THREE.MathUtils.clamp(viewYaw - deltaX * 0.0055, -maxViewYaw, maxViewYaw);
      viewPitch = THREE.MathUtils.clamp(viewPitch + deltaY * 0.004, -0.9, 0.9);
      lastPointerX = event.clientX;
      lastPointerY = event.clientY;
    };
    const onPointerUp = () => { dragging = false; };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointermove", onPointerMove, { capture: true, passive: false });
    document.addEventListener("pointerup", onPointerUp, true);
    document.addEventListener("pointercancel", onPointerUp, true);

    const animate = (time: number) => {
      frame = requestAnimationFrame(animate);
      if (document.hidden) return;
      if (introducing) {
        const t = THREE.MathUtils.clamp((time - introStart) / introDuration, 0, 1);
        const shot = t < 0.33 ? 0 : t < 0.88 ? 1 : t < 0.95 ? 2 : 3;
        if (shot !== activeIntroShot) {
          activeIntroShot = shot;
          camera.fov = shot === 1 ? 66 : 48;
          camera.updateProjectionMatrix();
          introShotCallback?.(shot);
        }
        if (shot === 0) {
          camera.position.copy(introHallCamera);
          camera.lookAt(0, 2.0, -19.1);
        } else if (shot === 1) {
          camera.position.copy(introStageCamera);
          camera.lookAt(0, 2.0, -5.8);
        } else {
          camera.position.copy(seatPosition);
          const seatedProgress = THREE.MathUtils.smoothstep(t, 0.72, 1);
          look.lerpVectors(introSeatLookStart, seatTarget, seatedProgress);
          camera.lookAt(look);
        }

        const entranceWalk = THREE.MathUtils.smoothstep(t, 0.08, 0.3);
        const hallwayWalk = THREE.MathUtils.smoothstep(t, 0.34, 0.65);
        const stageWalk = THREE.MathUtils.smoothstep(t, 0.65, 0.89);
        if (t < 0.08) founder.group.position.z = -21.45;
        else if (t < 0.3) founder.group.position.z = THREE.MathUtils.lerp(-21.45, -17.75, entranceWalk);
        else if (t < 0.34) founder.group.position.z = -17.75;
        else if (t < 0.65) founder.group.position.z = THREE.MathUtils.lerp(-17.75, -11.15, hallwayWalk);
        else founder.group.position.z = THREE.MathUtils.lerp(-11.15, -4.42, stageWalk);
        const walking = (t > 0.08 && t < 0.3) || (t > 0.34 && t < 1);
        const stride = walking ? 0.2 : 0.025;
        founder.legs.forEach((leg, index) => { leg.rotation.z = Math.sin(time * 0.016 + index * Math.PI) * stride; });
        founder.eyes.rotation.y = Math.sin(time * 0.0012) * 0.045;
        const entranceDoors = THREE.MathUtils.smoothstep(t, 0.02, 0.08) * (1 - THREE.MathUtils.smoothstep(t, 0.3, 0.36));
        const stageDoors = THREE.MathUtils.smoothstep(t, 0.57, 0.65) * (1 - THREE.MathUtils.smoothstep(t, 0.93, 1));
        hallLeftDoor.rotation.y = entranceDoors * 1.08;
        hallRightDoor.rotation.y = -entranceDoors * 1.08;
        leftDoor.rotation.y = -stageDoors * 1.08;
        rightDoor.rotation.y = stageDoors * 1.08;
        if (t >= 1) finishIntro();
      } else if (manualView) {
        camera.position.copy(seatPosition);
        camera.fov += (seatedViewFov - camera.fov) * 0.14;
        camera.updateProjectionMatrix();
        direction.set(Math.sin(viewYaw) * Math.cos(viewPitch), Math.sin(viewPitch), -Math.cos(viewYaw) * Math.cos(viewPitch));
        camera.lookAt(seatPosition.clone().add(direction));
      } else {
        camera.position.copy(seatPosition);
        const targetFov = selectedSpeaker !== null && selectedSpeaker > 0 ? 56 : seatedViewFov;
        camera.fov += (targetFov - camera.fov) * 0.14;
        camera.updateProjectionMatrix();
        if (selectedSpeaker !== null && selectedSpeaker > 0 && actors[selectedSpeaker]) {
          actors[selectedSpeaker].group.getWorldPosition(speakerLook);
          speakerLook.y += 2.5;
          tiltLookTargetDown(speakerLook);
          normalLook.lerp(speakerLook, 0.08);
        } else {
          normalLook.lerp(seatTarget, 0.08);
        }
        camera.lookAt(normalLook);
        founder.group.position.z = -4.42;
        founder.legs.forEach((leg, index) => { leg.rotation.z = Math.sin(time * 0.0017 + index * Math.PI) * 0.022; });
        founder.eyes.rotation.y = Math.sin(time * 0.0011) * 0.035;
        leftDoor.rotation.y *= 0.88;
        rightDoor.rotation.y *= 0.88;
        hallLeftDoor.rotation.y *= 0.88;
        hallRightDoor.rotation.y *= 0.88;
      }
      founder.group.position.y = 0.4 + Math.sin(time * 0.0017) * 0.015;
      speechBubbles[0].sprite.position.set(founder.group.position.x, founder.group.position.y + 3.55, founder.group.position.z + 0.05);
      actorLights[0].position.set(founder.group.position.x, founder.group.position.y + 3.0, founder.group.position.z + 0.7);
      sharks.forEach((actor, index) => {
        actor.eyes.rotation.y = selectedSpeaker === index + 1 ? Math.sin(time * 0.003) * 0.16 : Math.sin(time * 0.0007 + index) * 0.035;
        actor.legs.forEach((leg, legIndex) => { leg.rotation.z = Math.sin(time * 0.001 + legIndex * Math.PI + index) * 0.014; });
      });
      actorLights.forEach((light, index) => {
        const target = selectedSpeaker === index ? 12 : 0;
        light.intensity += (target - light.intensity) * 0.12;
      });
      spotlights[1].intensity = 155 + Math.sin(time * 0.0015) * 6;
      dust.rotation.y = Math.sin(time * 0.00013) * 0.035;
      renderer.render(scene, camera);
    };
    frame = requestAnimationFrame(animate);

    return {
      setPitch(archetype, company) {
        if (!archetype) {
          introducing = false;
          introCompleteCallback = null;
          introShotCallback = null;
          activeIntroShot = -1;
          manualView = false;
          dragging = false;
          viewYaw = 0;
          viewPitch = 0;
          selectedSpeaker = null;
          normalLook.copy(seatTarget);
          camera.position.copy(seatPosition);
          camera.fov = 48;
          camera.updateProjectionMatrix();
          founder.group.position.set(0, 0.4, -4.42);
          leftDoor.rotation.y = 0;
          rightDoor.rotation.y = 0;
          hallLeftDoor.rotation.y = 0;
          hallRightDoor.rotation.y = 0;
        }
        const shellColors: Record<string, number> = {
          "THE TRAP": 0xe5222b,
          "THE NEGOTIATOR": 0xf03b31,
          "THE UNICORN": 0xc91d28,
          "THE WILDCARD": 0xdd3b42,
        };
        founder.shell.color.setHex(shellColors[archetype] || 0xe5222b);
        drawSign(company);
      },
      mount,
      setSpeaker(index, text = "", speakerName = "") {
        speechBubbles.forEach((bubble) => { bubble.sprite.visible = false; });
        activeBubble.current = null;
        activeBubbleSpeaker = "";
        if (index !== null && index >= 0) manualView = false;
        selectedSpeaker = index !== null && index >= 0 ? index : null;
        if (index === null || index < 0) return;
        const bubble = speechBubbles[index];
        if (!bubble) return;
        activeBubbleSpeaker = speakerName;
        drawBubble(bubble, text, activeBubbleSpeaker);
        bubble.sprite.visible = true;
        activeBubble.current = bubble;
      },
      updateSpeech(text) {
        if (activeBubble.current) drawBubble(activeBubble.current, text, activeBubbleSpeaker);
      },
      intro(onComplete, onShotChange) {
        introducing = false;
        manualView = false;
        dragging = false;
        viewYaw = 0;
        viewPitch = 0;
        selectedSpeaker = null;
        introCompleteCallback = onComplete || null;
        introShotCallback = onShotChange || null;
        activeIntroShot = -1;
        camera.position.copy(seatPosition);
        camera.fov = 48;
        camera.updateProjectionMatrix();
        normalLook.copy(seatTarget);
        speechBubbles.forEach((bubble) => { bubble.sprite.visible = false; });
        activeBubble.current = null;
        founder.group.position.z = -21.45;
        leftDoor.rotation.y = 0;
        rightDoor.rotation.y = 0;
        hallLeftDoor.rotation.y = 0;
        hallRightDoor.rotation.y = 0;
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          activeIntroShot = 2;
          introShotCallback?.(2);
          founder.group.position.z = -4.42;
          introCompleteCallback?.();
          introCompleteCallback = null;
          introShotCallback = null;
          activeIntroShot = -1;
          return;
        }
        introStart = performance.now();
        introducing = true;
      },
      skipIntro() { finishIntro(); },
      dispose() {
        cancelAnimationFrame(frame);
        observer.disconnect();
        document.removeEventListener("pointerdown", onPointerDown, true);
        document.removeEventListener("pointermove", onPointerMove, true);
        document.removeEventListener("pointerup", onPointerUp, true);
        document.removeEventListener("pointercancel", onPointerUp, true);
        const geometries = new Set<THREE.BufferGeometry>();
        const materials = new Set<THREE.Material>();
        scene.traverse((object) => {
          if (object instanceof THREE.Mesh || object instanceof THREE.Points) {
            geometries.add(object.geometry);
            const material = object.material;
            if (Array.isArray(material)) material.forEach((item) => materials.add(item));
            else materials.add(material);
          }
        });
        geometries.forEach((geometry) => geometry.dispose());
        materials.forEach((material) => material.dispose());
        signTexture.dispose();
        woodTexture.dispose();
        skylineTexture.dispose();
        speechBubbles.forEach((bubble) => bubble.texture.dispose());
        renderer.dispose();
        renderer.domElement.remove();
      },
    };
  } catch (error) {
    console.warn("3D studio unavailable; continuing with the game interface.", error);
    return null;
  }
}
