const THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
const canvas = document.querySelector("#office3d");
const stage = canvas?.parentElement;
const statusMessage = document.querySelector("#office3d-status");
const floorButtons = document.querySelector("#office-floor-buttons");
const floorHeading = document.querySelector("#office-floor-heading");
const floorSummary = document.querySelector("#office-floor-summary");
const floorAgents = document.querySelector("#office-floor-agents");
const agentDetail = document.querySelector("#office-agent-detail");
const cameraButton = document.querySelector("#office-camera-mode");
const agentTooltip = document.querySelector("#office-agent-tooltip");
const FLOOR_COUNT = 6;
const FLOOR_HEIGHT = 1.12;
const FLOOR_NAMES = [
  "Núcleo Neris",
  "Negócios e crescimento",
  "Automação industrial",
  "Engenharia e confiabilidade",
  "Central JA e atendimento",
  "Segurança e auditoria",
];
const STATUS_COLORS = {
  running: 0xff6a00,
  error: 0xff2a1f,
  idle: 0xf3efe4,
  paused: 0xffc400,
  offline: 0x747474,
  pendente_integracao: 0x8c8990,
};

if (canvas && stage) {
  import(THREE_URL)
    .then((THREE) => startOffice(THREE))
    .catch((error) => {
      statusMessage.textContent = `Cena 3D indisponível: ${error.message}`;
      statusMessage.dataset.state = "error";
    });
}

function startOffice(THREE) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070707);
  scene.fog = new THREE.FogExp2(0x070707, 0.027);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 90);
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: "low-power",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene.add(new THREE.HemisphereLight(0xffe6cf, 0x15100c, 2.1));
  const keyLight = new THREE.DirectionalLight(0xffd0a1, 3.2);
  keyLight.position.set(7, 11, 8);
  keyLight.castShadow = true;
  scene.add(keyLight);

  const orangeLight = new THREE.PointLight(0xff6a00, 50, 20, 2);
  orangeLight.position.set(-5, 3, 5);
  scene.add(orangeLight);
  const redLight = new THREE.PointLight(0xff2a1f, 35, 18, 2);
  redLight.position.set(5, 4, -4);
  scene.add(redLight);

  const floorMaterial = new THREE.MeshStandardMaterial({
    color: 0x171411,
    metalness: 0.72,
    roughness: 0.31,
  });
  const glassMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xff7a22,
    metalness: 0.15,
    roughness: 0.19,
    transparent: true,
    opacity: 0.19,
    clearcoat: 1,
    side: THREE.DoubleSide,
  });
  const trimMaterial = new THREE.MeshStandardMaterial({
    color: 0xff6a00,
    emissive: 0xff3a00,
    emissiveIntensity: 1.2,
    metalness: 0.35,
    roughness: 0.28,
  });
  const floorGroups = [];
  const floorTargets = [];
  const markers = [];
  const activeLines = [];
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const cameraTarget = new THREE.Vector3(0, 3.1, 0);
  let agents = [];
  let logs = [];
  let selectedFloor = 0;
  let selectedAgentId = "";
  let firstPerson = false;
  let yaw = 0;
  let pitch = 0;
  let orbitRadius = 18;
  let orbitTheta = 0.64;
  let orbitPhi = 1.02;
  let dragStart = null;
  let dragMoved = false;
  const heldKeys = new Set();

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(200, 200),
    new THREE.MeshStandardMaterial({ color: 0x080808, metalness: 0.3, roughness: 0.85 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.23;
  ground.receiveShadow = true;
  scene.add(ground);

  const groundRing = new THREE.Mesh(
    new THREE.TorusGeometry(4.3, 0.025, 8, 120),
    new THREE.MeshBasicMaterial({ color: 0xff4b12, transparent: true, opacity: 0.55 }),
  );
  groundRing.rotation.x = Math.PI / 2;
  groundRing.position.y = -0.18;
  scene.add(groundRing);

  const createFloor = (index) => {
    const group = new THREE.Group();
    group.position.y = index * FLOOR_HEIGHT;
    const slab = new THREE.Mesh(new THREE.BoxGeometry(5.2, 0.11, 3.7), floorMaterial);
    slab.position.y = 0;
    slab.castShadow = true;
    slab.receiveShadow = true;
    slab.userData = { kind: "floor", floor: index };
    group.add(slab);
    floorTargets.push(slab);

    const ceiling = new THREE.Mesh(new THREE.BoxGeometry(5.1, 0.035, 3.6), trimMaterial);
    ceiling.position.y = 0.72;
    group.add(ceiling);

    for (const [x, z, width, depth] of [
      [0, -1.82, 5.1, 0.055],
      [-2.57, 0, 0.055, 3.6],
      [2.57, 0, 0.055, 3.6],
    ]) {
      const glass = new THREE.Mesh(new THREE.BoxGeometry(width, 0.66, depth), glassMaterial);
      glass.position.set(x, 0.36, z);
      group.add(glass);
    }

    for (let desk = 0; desk < 4; desk += 1) {
      const x = (desk % 2) * 2 - 1;
      const z = Math.floor(desk / 2) * 1.15 - 0.35;
      const table = new THREE.Mesh(
        new THREE.BoxGeometry(0.82, 0.06, 0.42),
        new THREE.MeshStandardMaterial({ color: 0x26211b, metalness: 0.52, roughness: 0.42 }),
      );
      table.position.set(x, 0.24, z);
      table.castShadow = true;
      group.add(table);
    }

    const label = new THREE.Mesh(
      new THREE.BoxGeometry(5.25, 0.028, 0.08),
      new THREE.MeshBasicMaterial({ color: index % 2 ? 0xff2a1f : 0xff6a00 }),
    );
    label.position.set(0, 0.1, 1.88);
    group.add(label);
    group.userData.floor = index;
    scene.add(group);
    floorGroups.push(group);
  };

  for (let floor = 0; floor < FLOOR_COUNT; floor += 1) createFloor(floor);

  const towerCap = new THREE.Mesh(
    new THREE.BoxGeometry(3.2, 0.28, 2.4),
    new THREE.MeshStandardMaterial({ color: 0x21140d, metalness: 0.74, roughness: 0.24 }),
  );
  towerCap.position.set(0, FLOOR_COUNT * FLOOR_HEIGHT + 0.33, 0);
  towerCap.castShadow = true;
  scene.add(towerCap);

  const core = new THREE.Mesh(
    new THREE.OctahedronGeometry(0.24, 1),
    new THREE.MeshStandardMaterial({
      color: 0xff8a1a,
      emissive: 0xff4b00,
      emissiveIntensity: 2,
      metalness: 0.45,
      roughness: 0.2,
    }),
  );
  core.position.set(0, FLOOR_COUNT * FLOOR_HEIGHT + 0.9, 0);
  scene.add(core);
  const coreHalo = new THREE.Mesh(
    new THREE.TorusGeometry(0.42, 0.014, 8, 64),
    new THREE.MeshBasicMaterial({ color: 0xff3820, transparent: true, opacity: 0.8 }),
  );
  coreHalo.position.copy(core.position);
  coreHalo.rotation.x = Math.PI / 2;
  scene.add(coreHalo);

  const setCamera = () => {
    if (firstPerson) {
      const direction = new THREE.Vector3(
        Math.sin(yaw) * Math.cos(pitch),
        Math.sin(pitch),
        -Math.cos(yaw) * Math.cos(pitch),
      );
      camera.lookAt(camera.position.clone().add(direction));
      return;
    }
    camera.position.set(
      cameraTarget.x + orbitRadius * Math.sin(orbitPhi) * Math.sin(orbitTheta),
      cameraTarget.y + orbitRadius * Math.cos(orbitPhi),
      cameraTarget.z + orbitRadius * Math.sin(orbitPhi) * Math.cos(orbitTheta),
    );
    camera.lookAt(cameraTarget);
  };

  const resize = () => {
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  };
  new ResizeObserver(resize).observe(stage);
  resize();
  setCamera();

  const getFloorAgents = (floor) =>
    agents.filter((agent, index) => floorForAgent(agent, index) === floor);

  const floorForAgent = (agent, index) => {
    const identity = String(agent.id || "");
    if (/security|segur/i.test(identity) || identity === "agent-31" || identity === "agent-41") return 5;
    const number = Number(identity.match(/\d+/)?.[0]);
    if (Number.isFinite(number)) {
      if (number >= 1 && number <= 18) return 1;
      if (number >= 19 && number <= 23) return 2;
      if (number >= 24 && number <= 30) return 0;
      if (number >= 32 && number <= 37) return 3;
      if (number === 40) return 4;
      if (number === 38 || number === 39 || number === 42 || number === 43) return 1;
    }
    return index % FLOOR_COUNT;
  };

  const latestLog = (agent) =>
    logs.find((item) =>
      item.agente_id === agent.id ||
      item.nome_agente === agent.name ||
      item.nome_agente === agent.nome,
    );

  const statusLabel = (status) => ({
    running: "Executando tarefa atribuída",
    idle: "Online, aguardando tarefa",
    paused: "Pausado pelo operador",
    error: "Erro reportado pelo serviço",
    offline: "Worker offline",
    pendente_integracao: "Integração pendente",
  }[status] || `Estado informado pelo servidor: ${status || "indisponível"}`);

  const setSelectedAgent = (agent) => {
    if (!agent) return;
    selectedAgentId = agent.id;
    const activity = latestLog(agent);
    const name = agent.name || agent.nome || agent.id;
    const updated = agent.updated_at
      ? new Date(agent.updated_at).toLocaleString("pt-BR")
      : "horário não fornecido";
    floorSummary.textContent = `${getFloorAgents(selectedFloor).length} agente(s) neste andar · ${getFloorAgents(selectedFloor).filter((item) => item.status === "running").length} em execução`;
    agentDetail.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = name;
    const state = document.createElement("p");
    state.textContent = `${statusLabel(agent.status)} · atualizado ${updated}`;
    const log = document.createElement("p");
    log.textContent = activity
      ? `Último registro: ${activity.log_texto || activity.status_acao} · ${new Date(activity.created_at).toLocaleString("pt-BR")}`
      : "Sem registro recente associado a este agente.";
    const limitation = document.createElement("small");
    limitation.textContent = "Este serviço fornece status e logs; ele não transmite linhas de código ao vivo.";
    agentDetail.append(title, state, log, limitation);
    if (agent.id === "agent-31") {
      const analyzeButton = document.createElement("button");
      analyzeButton.type = "button";
      analyzeButton.className = "button secondary";
      analyzeButton.textContent = "Preparar análise defensiva";
      analyzeButton.addEventListener("click", () => {
        const selector = document.querySelector("#agent-select");
        const prompt = document.querySelector("#task-prompt");
        selector.value = agent.id;
        prompt.placeholder = "Cole código ou configuração autorizada para revisão defensiva";
        document.querySelector("#task-form").scrollIntoView({ behavior: "smooth", block: "center" });
        prompt.focus({ preventScroll: true });
      });
      agentDetail.append(analyzeButton);
    }
  };

  const showAgentTooltip = (agent, marker) => {
    const activity = latestLog(agent);
    const position = marker.body.getWorldPosition(new THREE.Vector3()).project(camera);
    const bounds = canvas.getBoundingClientRect();
    agentTooltip.style.left = `${(position.x * 0.5 + 0.5) * bounds.width}px`;
    agentTooltip.style.top = `${(-position.y * 0.5 + 0.5) * bounds.height}px`;
    agentTooltip.querySelector("strong").textContent = agent.name || agent.nome || agent.id;
    agentTooltip.querySelector("span").textContent =
      activity?.log_texto || statusLabel(agent.status);
    agentTooltip.querySelector("small").textContent =
      agent.status === "running"
        ? "Execução reportada pelo servidor · sem transmissão de código ao vivo"
        : statusLabel(agent.status);
    agentTooltip.hidden = false;
  };

  const renderFloor = (floor, focusCamera = false) => {
    selectedFloor = floor;
    const floorAgentsList = getFloorAgents(floor);
    floorHeading.textContent = `Andar ${floor + 1} · ${FLOOR_NAMES[floor]}`;
    floorSummary.textContent = `${floorAgentsList.length} agente(s) · ${floorAgentsList.filter((item) => item.status === "running").length} em execução`;
    floorAgents.replaceChildren();
    floorButtons.querySelectorAll("button").forEach((button) => {
      button.setAttribute("aria-pressed", String(Number(button.dataset.floor) === floor));
    });
    for (const agent of floorAgentsList) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "floor-agent";
      button.dataset.status = agent.status || "offline";
      const name = document.createElement("strong");
      name.textContent = agent.name || agent.nome || agent.id;
      const state = document.createElement("span");
      state.textContent = statusLabel(agent.status);
      button.append(name, state);
      button.addEventListener("click", () => setSelectedAgent(agent));
      floorAgents.append(button);
    }
    if (!floorAgentsList.length) {
      floorAgents.textContent = "Nenhum agente foi retornado para este andar.";
    }
    if (!floorAgentsList.some((agent) => agent.id === selectedAgentId)) {
      agentDetail.textContent = "Selecione um agente para ver o status e o último registro recebido.";
    } else {
      setSelectedAgent(floorAgentsList.find((agent) => agent.id === selectedAgentId));
    }
    if (focusCamera && firstPerson) moveToFloor(floor);
    if (focusCamera && !firstPerson) {
      cameraTarget.y = floor * FLOOR_HEIGHT + 0.32;
      setCamera();
    }
  };

  const renderFloorButtons = () => {
    floorButtons.replaceChildren();
    for (let floor = FLOOR_COUNT - 1; floor >= 0; floor -= 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "floor-button";
      button.dataset.floor = String(floor);
      button.setAttribute("aria-pressed", String(floor === selectedFloor));
      button.textContent = `Andar ${floor + 1} · ${getFloorAgents(floor).length}`;
      button.addEventListener("click", () => renderFloor(floor, true));
      floorButtons.append(button);
    }
  };

  const clearAgents = () => {
    const disposeObject = (object) => {
      object.traverse((child) => {
        child.geometry?.dispose();
        if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
        else child.material?.dispose();
      });
    };
    for (const marker of markers) {
      scene.remove(marker.group);
      disposeObject(marker.group);
    }
    for (const line of activeLines) {
      scene.remove(line.path);
      scene.remove(line.pulse);
      disposeObject(line.path);
      disposeObject(line.pulse);
    }
    markers.length = 0;
    activeLines.length = 0;
  };

  const updateAgents = (nextAgents) => {
    agents = Array.isArray(nextAgents) ? nextAgents : [];
    clearAgents();
    const floorSlots = Array(FLOOR_COUNT).fill(0);
    agents.forEach((agent, index) => {
      const floor = floorForAgent(agent, index);
      const slot = floorSlots[floor]++;
      const x = ((slot % 6) - 2.5) * 0.62;
      const z = (Math.floor(slot / 6) - 1.5) * 0.66;
      const color = STATUS_COLORS[agent.status] ?? STATUS_COLORS.offline;
      const group = new THREE.Group();
      group.position.set(x, floor * FLOOR_HEIGHT + 0.34, z);
      const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.11, 0.22, 3, 8),
        new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: agent.status === "running" ? 1.25 : 0.18,
          metalness: 0.35,
          roughness: 0.3,
        }),
      );
      body.userData = { kind: "agent", agentId: agent.id, floor };
      body.castShadow = true;
      group.add(body);
      const halo = new THREE.Mesh(
        new THREE.TorusGeometry(0.18, 0.012, 8, 40),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.75 }),
      );
      halo.rotation.x = Math.PI / 2;
      halo.position.y = -0.16;
      group.add(halo);
      scene.add(group);
      markers.push({ group, agent, body, floor });

      if (agent.status === "running") {
        const start = new THREE.Vector3(0, FLOOR_COUNT * FLOOR_HEIGHT + 0.72, 0);
        const end = group.position.clone();
        const curve = new THREE.QuadraticBezierCurve3(
          start,
          new THREE.Vector3(x * 0.55, (start.y + end.y) / 2, z * 0.55),
          end,
        );
        const path = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(curve.getPoints(28)),
          new THREE.LineBasicMaterial({ color: 0xff6a00, transparent: true, opacity: 0.55 }),
        );
        const pulse = new THREE.Mesh(
          new THREE.SphereGeometry(0.045, 10, 8),
          new THREE.MeshBasicMaterial({ color: 0xffc400 }),
        );
        scene.add(path, pulse);
        activeLines.push({ curve, path, pulse, phase: Math.random() });
      }
    });
    agents = Array.isArray(window.nerisAgents) ? window.nerisAgents : [];
    logs = Array.isArray(window.nerisLogs) ? window.nerisLogs : [];
    updateAgents(agents);
    renderFloorButtons();
    renderFloor(selectedFloor);
    renderDailyDiagnostic();
  };

  const renderDailyDiagnostic = () => {
    const day = new Date().toLocaleDateString("pt-BR");
    const today = logs.filter((item) => {
      const date = new Date(item.created_at);
      return Number.isFinite(date.getTime()) && date.toDateString() === new Date().toDateString();
    });
    const errors = today.filter((item) => String(item.status_acao).toLowerCase() === "error").length;
    const running = agents.filter((agent) => agent.status === "running").length;
    const waiting = agents.filter((agent) => agent.status === "idle").length;
    const offline = agents.filter((agent) => agent.status === "offline").length;
    document.querySelector("#diagnostic-date").textContent = `Registros de ${day} · amostra de até 100 eventos`;
    document.querySelector("#diagnostic-running").textContent = String(running);
    document.querySelector("#diagnostic-waiting").textContent = String(waiting);
    document.querySelector("#diagnostic-errors").textContent = String(errors);
    document.querySelector("#diagnostic-offline").textContent = String(offline);
    const description = errors
      ? `${errors} evento(s) de erro constam nos registros carregados hoje. Abra o console de atividade para investigar.`
      : today.length
        ? `Nenhum erro encontrado nos ${today.length} registro(s) de hoje carregados. Isso não substitui uma auditoria completa.`
        : "Nenhum evento de hoje foi retornado nos últimos 100 logs consultados.";
    document.querySelector("#diagnostic-summary").textContent =
      `${description} Estados de agentes são reportados pelo runtime FastAPI; não significam execução contínua de tarefas.`;
  };

  const moveToFloor = (floor) => {
    const height = floor * FLOOR_HEIGHT + 0.5;
    if (!firstPerson) return;
    camera.position.set(0, height, 2.1);
    yaw = 0;
    pitch = 0;
    setCamera();
  };

  const raycast = (event) => {
    const bounds = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(
      [...markers.map((marker) => marker.body), ...floorTargets],
      false,
    )[0];
    return hit?.object || null;
  };

  canvas.addEventListener("pointermove", (event) => {
    if (document.pointerLockElement === canvas) return;
    if (dragStart && !firstPerson) {
      if (Math.abs(event.clientX - dragStart.x) + Math.abs(event.clientY - dragStart.y) > 3) {
        dragMoved = true;
      }
      orbitTheta -= (event.clientX - dragStart.x) * 0.008;
      orbitPhi = THREE.MathUtils.clamp(
        orbitPhi + (event.clientY - dragStart.y) * 0.006,
        0.25,
        1.42,
      );
      dragStart = { x: event.clientX, y: event.clientY };
      setCamera();
      return;
    }
    const object = raycast(event);
    canvas.style.cursor = object ? "pointer" : "grab";
    if (object?.userData.kind === "agent") {
      const marker = markers.find((item) => item.agent.id === object.userData.agentId);
      if (marker) {
        setSelectedAgent(marker.agent);
        showAgentTooltip(marker.agent, marker);
      }
    } else {
      agentTooltip.hidden = true;
    }
  });
  canvas.addEventListener("pointerdown", (event) => {
    if (!firstPerson) {
      dragStart = { x: event.clientX, y: event.clientY };
      dragMoved = false;
    }
  });
  canvas.addEventListener("pointerup", (event) => {
    const moved = dragMoved;
    dragStart = null;
    dragMoved = false;
    if (moved) return;
    if (document.pointerLockElement === canvas) return;
    const object = raycast(event);
    if (object?.userData.kind === "floor") {
      agentTooltip.hidden = true;
      renderFloor(object.userData.floor, true);
    }
    if (object?.userData.kind === "agent") {
      const marker = markers.find((item) => item.agent.id === object.userData.agentId);
      if (marker) {
        renderFloor(marker.floor, true);
        setSelectedAgent(marker.agent);
        showAgentTooltip(marker.agent, marker);
      }
    }
  });
  canvas.addEventListener("wheel", (event) => {
    if (firstPerson) return;
    event.preventDefault();
    orbitRadius = THREE.MathUtils.clamp(orbitRadius + event.deltaY * 0.008, 7, 24);
    setCamera();
  }, { passive: false });

  cameraButton.addEventListener("click", () => {
    firstPerson = !firstPerson;
    cameraButton.textContent = firstPerson ? "Sair da câmera interna" : "Entrar no andar";
    cameraButton.setAttribute("aria-pressed", String(firstPerson));
    if (firstPerson) {
      moveToFloor(selectedFloor);
      statusMessage.textContent = "Câmera interna ativa · WASD move · mouse olha · Esc sai do cursor";
      canvas.requestPointerLock?.();
    } else {
      document.exitPointerLock?.();
      statusMessage.textContent = "Visão externa · arraste para orbitar · clique em um andar";
      setCamera();
    }
  });

  canvas.addEventListener("click", () => {
    if (firstPerson && document.pointerLockElement !== canvas) canvas.requestPointerLock?.();
  });
  document.addEventListener("pointerlockchange", () => {
    agentTooltip.hidden = true;
    if (document.pointerLockElement !== canvas && firstPerson) {
      statusMessage.textContent = "Câmera interna ativa · clique no prédio para retomar o mouse";
    }
  });
  document.addEventListener("mousemove", (event) => {
    if (!firstPerson || document.pointerLockElement !== canvas) return;
    yaw -= event.movementX * 0.0025;
    pitch = THREE.MathUtils.clamp(pitch - event.movementY * 0.002, -1.1, 1.1);
    setCamera();
  });
  document.addEventListener("keydown", (event) => {
    if (!firstPerson || document.pointerLockElement !== canvas) return;
    if (["w", "a", "s", "d"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      heldKeys.add(event.key.toLowerCase());
    }
  });
  document.addEventListener("keyup", (event) => heldKeys.delete(event.key.toLowerCase()));

  const moveCamera = (delta) => {
    if (!firstPerson) return;
    const forward = new THREE.Vector3(Math.sin(yaw), 0, -Math.cos(yaw));
    const right = new THREE.Vector3(Math.cos(yaw), 0, Math.sin(yaw));
    const speed = delta * 2.2;
    if (heldKeys.has("w")) camera.position.addScaledVector(forward, speed);
    if (heldKeys.has("s")) camera.position.addScaledVector(forward, -speed);
    if (heldKeys.has("a")) camera.position.addScaledVector(right, -speed);
    if (heldKeys.has("d")) camera.position.addScaledVector(right, speed);
    camera.position.x = THREE.MathUtils.clamp(camera.position.x, -2.2, 2.2);
    camera.position.z = THREE.MathUtils.clamp(camera.position.z, -1.4, 1.4);
  };

  let previousTime = 0;
  const animate = (time) => {
    requestAnimationFrame(animate);
    const delta = Math.min((time - previousTime) / 1000, 0.05);
    previousTime = time;
    moveCamera(delta);
    if (firstPerson && document.pointerLockElement === canvas) setCamera();
    core.rotation.y += delta * 0.42;
    core.rotation.x += delta * 0.12;
    coreHalo.rotation.z += delta * 0.18;
    groundRing.material.opacity = 0.48 + Math.sin(time * 0.0015) * 0.12;
    for (const line of activeLines) {
      line.phase = (line.phase + delta * 0.42) % 1;
      line.pulse.position.copy(line.curve.getPoint(line.phase));
    }
    renderer.render(scene, camera);
  };
  requestAnimationFrame(animate);

  window.addEventListener("resize", resize);
  window.addEventListener("neris:agents-updated", (event) => updateAgents(event.detail));
  window.addEventListener("neris:logs-updated", (event) => {
    logs = Array.isArray(event.detail) ? event.detail : [];
    renderFloor(selectedFloor);
    renderDailyDiagnostic();
    if (selectedAgentId) {
      const selectedAgent = agents.find((agent) => agent.id === selectedAgentId);
      if (selectedAgent) setSelectedAgent(selectedAgent);
    }
  });
  renderFloorButtons();
  renderFloor(selectedFloor);
  statusMessage.textContent = "Visão externa · arraste para orbitar · clique em um andar";
  statusMessage.dataset.state = "ready";
  window.dispatchEvent(new CustomEvent("neris:office-ready"));
}
