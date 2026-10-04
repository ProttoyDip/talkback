/*
 * "Storm": TalkBack's presence orb. A breathing plasma sphere of 50,000
 * additive points (crimson core, magenta, gold rim), ported from the supplied
 * Three.js scene with its shaders, colours and postprocessing unchanged.
 *
 * Differences from the original full-page scene, all because it is a small
 * indicator instead of the page:
 *  - It renders into a small square canvas. Point size scales with that
 *    canvas, so the orb keeps the look of the full-window original.
 *  - It reacts only to the conversation: it swells and pulses with the live
 *    voice while the user speaks and while TalkBack answers. There is no
 *    scroll dive, cursor void or parallax.
 *  - It can render one still frame (reduced motion) and be disposed.
 */
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { CopyShader } from 'three/examples/jsm/shaders/CopyShader.js'
import { GammaCorrectionShader } from 'three/examples/jsm/shaders/GammaCorrectionShader.js'

const CONFIG = {
  bgColor: '#1a0418',
  flameColor: '#ff2d6b',
  flameColor2: '#ffd36b',
  flameAmt: 0.2,
  atmoColor: '#ff7ab0',
  atmoCount: 300,
  atmoSize: 24,
  atmoSpeed: 1.0,
  coreColor: '#6a0a2a',
  midColor: '#ff2d6b',
  rimColor: '#ffd36b',
  opacity: 2,
  pointSize: 80,
  brightness: 1.6,
  spin: 0.03,
  blowUp: 0,
  repelRadius: 1.4,
  repelStrength: 4,
  scrollDive: 3,
  scrollGrow: 0.5,
  scrollSpin: 0.6,
  parallax: 0.7,
}

/** The original was tuned for a full window about 900 css px tall. */
const REFERENCE_HEIGHT = 900
/*
 * The original camera sits at z = 7, where the sphere fills the frame. A
 * contained orb needs a margin around it, so the camera starts further back.
 */
const CAMERA_Z = 9.5

const LAYERS = { NONE: 0, TORUS_SCENE: 1, BLOOM_SCENE: 2, ENTIRE_SCENE: 3 }
const Lerp = (a: number, b: number, t: number) => a + (b - a) * t
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

function hexToVec3(hex: string) {
  const n = parseInt(hex.slice(1), 16)
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255)
}

const STORM_VERTEX = /* glsl */ `
uniform float uTime; uniform float uSize; uniform float uBlowUp;
uniform vec3 uCursor; uniform float uRepelRadius; uniform float uRepelStrength; uniform float uActivity;
uniform vec3 uCore; uniform vec3 uMid; uniform vec3 uRim;
attribute float aScale; attribute float aNoise; attribute float aRadialPush; attribute float aMix;
varying vec3 vColor; varying float vBlowUp;
void main() {
  vec3 pos = position;

  // Per-particle in/out wobble.
  float t = uTime * 1.4 + aNoise * 6.2831;
  float wobble = sin(t) * 0.1 * aRadialPush;
  pos *= 1.0 + wobble;

  // Slow secondary swirl on xz.
  float swirlAngle = uTime * 0.05 + aNoise * 6.2831;
  mat2 swirl = mat2(cos(swirlAngle), -sin(swirlAngle), sin(swirlAngle), cos(swirlAngle));
  pos.xz = swirl * pos.xz;

  // Blow-up — radial explosion with a squared falloff.
  vec3 outward = normalize(pos + vec3(0.0001));
  float blow = uBlowUp * uBlowUp;
  pos += outward * blow * (10.0 + aNoise * 18.0) * aRadialPush;

  vec4 modelPosition = modelMatrix * vec4(pos, 1.0);

  vec3 toParticle = modelPosition.xyz - uCursor;
  float dist = length(toParticle);
  float falloff = smoothstep(uRepelRadius, 0.0, dist);
  modelPosition.xyz += normalize(toParticle + vec3(0.0001)) * falloff * uRepelStrength * uActivity;

  vec4 viewPosition = viewMatrix * modelPosition;
  gl_Position = projectionMatrix * viewPosition;
  gl_PointSize = uSize * aScale;
  gl_PointSize *= (1.0 / -viewPosition.z);

  // Three-stop radial gradient (aMix = biased radius 0..1).
  float t1 = smoothstep(0.25, 0.85, aMix);
  vec3 mix1 = mix(uCore, uMid, t1);
  float t2 = clamp((aMix - 0.7) * 3.0, 0.0, 1.0);
  vColor = mix(mix1, uRim, t2);
  vBlowUp = uBlowUp;
}
`

const STORM_FRAGMENT = /* glsl */ `
uniform float uOpacity; uniform float uBrightness;
varying vec3 vColor; varying float vBlowUp;
void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  if (d > 0.5) discard;
  float strength = pow(1.0 - d * 2.0, 4.5);
  vec3 color = mix(vec3(0.0), vColor, strength);
  float blowFade = 1.0 - smoothstep(0.15, 1.0, vBlowUp);
  gl_FragColor = vec4(color * uBrightness, strength * uOpacity * blowFade);
}
`

const FINAL_VERTEX = /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }`

const FINAL_FRAGMENT = /* glsl */ `
uniform float iTime; uniform sampler2D tDiffuse; uniform sampler2D bloomTexture; uniform sampler2D torusTexture; uniform sampler2D haloTexture;
uniform vec3 uBg; uniform vec3 uFlameA; uniform vec3 uFlameB; uniform float uFlameAmt;
varying vec2 vUv;
vec3 warp3d(vec3 pos, float t){ float curv=.8,a=1.9,b=0.7; pos*=2.;
  pos.x+=curv*sin(t+a*pos.y)+t*b; pos.y+=curv*cos(t+a*pos.x);
  pos.y+=curv*sin(t+a*pos.z)+t*b; pos.z+=curv*cos(t+a*pos.y);
  pos.z+=curv*sin(t+a*pos.x)+t*b; pos.x+=curv*cos(t+a*pos.z);
  return 0.5+0.5*cos(pos.xyz+vec3(1,2,4)); }
void main(){
  vec2 uv = 2.*vUv - 1.;
  vec3 w = pow(warp3d(vec3(uv.x, sin(uv.y), uv.y), iTime*1.5), vec3(1.5));
  vec3 flame = 1.5*uFlameA*w.x; flame*=w.y; flame += uFlameB*w.z;
  flame *= smoothstep(0.25, 1., abs(uv.y));
  float md = smoothstep(-0.7, 1., -uv.y*uv.x); flame *= md*md;
  vec3 bg = uBg * (1.0 - 0.4 * length(uv));
  vec3 halo = texture2D(haloTexture, vUv).xyz;
  gl_FragColor = vec4(bg + flame*uFlameAmt + texture2D(bloomTexture, vUv).xyz + texture2D(torusTexture, vUv).xyz + texture2D(tDiffuse, vUv).xyz + halo, 1.);
}
`

const MOTES_VERTEX = /* glsl */ `
attribute float size; attribute float seed; uniform float uTime; uniform vec2 uRes;
varying float vA;
vec3 warp(vec3 p, float t){ float c=0.9,a=1.9,b=0.02,s=0.05; p*=2.;
  p.x+=c*sin(s*t+a*p.y)+t*b; p.y+=c*cos(s*t+a*p.x); p.y+=c*sin(s*t+a*p.z)+t*b;
  p.z+=c*cos(s*t+a*p.y); p.z+=c*sin(s*t+a*p.x)+t*b; p.x+=c*cos(s*t+a*p.z);
  return cos(p+vec3(1,2,4)); }
void main(){
  vec3 v = position*4.0 + warp(position, uTime)*1.2;
  vec4 mv = modelViewMatrix * vec4(v, 1.0);
  float r = length(v); float farF = 1.0 - smoothstep(5.0, 6.5, r); float nearF = smoothstep(0.0, 0.5, -mv.z);
  vA = farF * nearF;
  gl_PointSize = size * uRes.y / 900.0 / -mv.z; gl_PointSize = max(gl_PointSize, 1.0);
  gl_Position = projectionMatrix * mv;
}
`

const MOTES_FRAGMENT = /* glsl */ `
uniform vec3 uColor; varying float vA;
void main(){ vec2 p = gl_PointCoord - 0.5; float l = length(p); if (l > 0.5) discard;
  float tex = smoothstep(0.5, 0.0, l); gl_FragColor = vec4(uColor * tex, tex * vA * 0.6); }
`

/** How the orb behaves in a conversation state. */
export interface OrbMood {
  /** 0..1: the original's scroll dive. Grows the orb a little. */
  dive: number
  /** 0..1: how strongly the live voice level makes it pulse. */
  pulse: number
  /** 0..1: overall brightness (offline and muted dim it). */
  presence: number
}

export interface StormOrb {
  setMood: (mood: OrbMood) => void
  dispose: () => void
}

/**
 * Starts the orb on `canvas` (square). `level` returns the live voice level
 * (0..1) each frame. With `still` it draws one frame and stops. Returns null
 * when WebGL is not available.
 */
export function createStormOrb(
  canvas: HTMLCanvasElement,
  level: () => number,
  still: boolean,
): StormOrb | null {
  let renderer: THREE.WebGL1Renderer
  try {
    renderer = new THREE.WebGL1Renderer({ canvas, antialias: true })
  } catch {
    return null
  }
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.VSMShadowMap

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x000000)
  scene.fog = new THREE.Fog(0x000000, 0, 15)

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 80)
  camera.position.set(0, 0, CAMERA_Z)
  camera.layers.enable(LAYERS.TORUS_SCENE)
  camera.layers.enable(LAYERS.BLOOM_SCENE)
  camera.layers.enable(LAYERS.ENTIRE_SCENE)
  scene.add(camera)

  // The storm cloud.
  const count = 50000
  const radius = 2.5
  const positions = new Float32Array(count * 3)
  const scales = new Float32Array(count)
  const noises = new Float32Array(count)
  const radialPush = new Float32Array(count)
  const mixv = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    const i3 = i * 3
    let u: number, v: number, s: number
    // Marsaglia: uniform point on the unit sphere
    do {
      u = Math.random() * 2 - 1
      v = Math.random() * 2 - 1
      s = u * u + v * v
    } while (s >= 1 || s === 0)
    const factor = 2 * Math.sqrt(1 - s)
    const dx = u * factor
    const dy = v * factor
    const dz = 1 - 2 * s
    const rN = Math.pow(Math.random(), 0.4) // bias outward (most points near the shell)
    const r = radius * (0.55 + rN * 0.45)
    positions[i3] = dx * r
    positions[i3 + 1] = dy * r
    positions[i3 + 2] = dz * r
    mixv[i] = rN
    scales[i] = 0.45 + Math.random() * 0.8
    noises[i] = Math.random()
    radialPush[i] = 0.4 + rN * 1.1
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('aScale', new THREE.Float32BufferAttribute(scales, 1))
  geometry.setAttribute('aNoise', new THREE.Float32BufferAttribute(noises, 1))
  geometry.setAttribute('aRadialPush', new THREE.Float32BufferAttribute(radialPush, 1))
  geometry.setAttribute('aMix', new THREE.Float32BufferAttribute(mixv, 1))

  const uniforms = {
    uTime: { value: 0 },
    uSize: { value: CONFIG.pointSize },
    uOpacity: { value: 0 },
    uBlowUp: { value: CONFIG.blowUp },
    uCursor: { value: new THREE.Vector3() },
    uRepelRadius: { value: CONFIG.repelRadius },
    uRepelStrength: { value: CONFIG.repelStrength },
    uActivity: { value: 0 },
    uCore: { value: hexToVec3(CONFIG.coreColor) },
    uMid: { value: hexToVec3(CONFIG.midColor) },
    uRim: { value: hexToVec3(CONFIG.rimColor) },
    uBrightness: { value: CONFIG.brightness },
  }
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms,
    vertexShader: STORM_VERTEX,
    fragmentShader: STORM_FRAGMENT,
  })
  const points = new THREE.Points(geometry, material)
  points.layers.enable(LAYERS.ENTIRE_SCENE)
  const group = new THREE.Group()
  group.add(points)
  scene.add(group)

  // Ambient motes that follow the camera.
  const motes = (() => {
    const n = Math.round(CONFIG.atmoCount)
    const pos = new Float32Array(n * 3)
    const sizes = new Float32Array(n)
    const seeds = new Float32Array(n)
    for (let i = 0; i < n; i++) {
      pos[i * 3] = 2 * Math.random() - 1
      pos[i * 3 + 1] = 2 * Math.random() - 1
      pos[i * 3 + 2] = 2 * Math.random() - 1
      sizes[i] = CONFIG.atmoSize * (0.4 + Math.random())
      seeds[i] = Math.random()
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    geo.setAttribute('seed', new THREE.BufferAttribute(seeds, 1))
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: false,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: hexToVec3(CONFIG.atmoColor) },
        uRes: { value: new THREE.Vector2(1, 1) },
      },
      vertexShader: MOTES_VERTEX,
      fragmentShader: MOTES_FRAGMENT,
    })
    const pts = new THREE.Points(geo, mat)
    pts.frustumCulled = false
    pts.layers.enable(LAYERS.ENTIRE_SCENE)
    scene.add(pts)
    return { pts, mat, geo }
  })()

  // Three composers share one RenderPass.
  const renderScene = new RenderPass(scene, camera)
  const size = new THREE.Vector2(1, 1)

  const torusComposer = new EffectComposer(renderer)
  torusComposer.renderToScreen = false
  torusComposer.addPass(renderScene)
  torusComposer.addPass(new ShaderPass(GammaCorrectionShader))
  torusComposer.addPass(new UnrealBloomPass(size.clone(), 0.22, 0.2, 0))
  torusComposer.addPass(new ShaderPass(CopyShader))

  const bloomComposer = new EffectComposer(renderer)
  bloomComposer.renderToScreen = false
  bloomComposer.addPass(renderScene)
  bloomComposer.addPass(new UnrealBloomPass(size.clone(), 0.4, 0.55, 0))
  bloomComposer.addPass(new ShaderPass(GammaCorrectionShader))

  const finalPass = new ShaderPass(
    new THREE.ShaderMaterial({
      uniforms: {
        iTime: { value: 0 },
        tDiffuse: { value: null },
        torusTexture: { value: null },
        bloomTexture: { value: null },
        haloTexture: { value: null },
        uBg: { value: hexToVec3(CONFIG.bgColor) },
        uFlameA: { value: hexToVec3(CONFIG.flameColor) },
        uFlameB: { value: hexToVec3(CONFIG.flameColor2) },
        uFlameAmt: { value: CONFIG.flameAmt },
      },
      vertexShader: FINAL_VERTEX,
      fragmentShader: FINAL_FRAGMENT,
    }),
  )
  const finalComposer = new EffectComposer(renderer)
  finalComposer.addPass(renderScene)
  finalComposer.addPass(finalPass)
  finalPass.uniforms.bloomTexture.value = bloomComposer.renderTarget1.texture
  finalPass.uniforms.torusTexture.value = torusComposer.renderTarget1.texture

  // State
  let mood: OrbMood = { dive: 0, pulse: 0, presence: 1 }
  let diveSmooth = 0
  let diveCurrent = 0
  let presence = 1
  let voice = 0
  // Larger points overlap more; this keeps the additive glow from blowing out.
  let opacityScale = 1
  let t0 = performance.now() / 1000
  const appearStart = performance.now()

  function update() {
    const t = performance.now() / 1000
    const dt = Math.min(0.05, t - t0)
    t0 = t
    uniforms.uTime.value = t

    const scroll = diveCurrent
    camera.position.set(0, 0, CAMERA_Z - scroll * CONFIG.scrollDive)
    camera.lookAt(0, 0, 0)
    // The live voice swells the orb while someone is speaking.
    group.scale.setScalar((1 + scroll * CONFIG.scrollGrow) * (1 + voice * 0.3 * mood.pulse))
    const elapsed = performance.now() - appearStart
    const fade = still ? 1 : Math.max(0, Math.min(1, (elapsed - 300) / 1400))
    uniforms.uOpacity.value = fade * CONFIG.opacity * presence * opacityScale
    uniforms.uBlowUp.value = CONFIG.blowUp
    group.rotation.y += dt * (CONFIG.spin + scroll * CONFIG.scrollSpin)
    group.rotation.x += dt * CONFIG.spin * 0.33

    motes.mat.uniforms.uTime.value = t * CONFIG.atmoSpeed * 8.0
    motes.pts.position.copy(camera.position)
    finalPass.uniforms.iTime.value = t
  }

  function draw() {
    update()
    camera.layers.set(LAYERS.TORUS_SCENE)
    torusComposer.render()
    camera.layers.set(LAYERS.BLOOM_SCENE)
    bloomComposer.render()
    camera.layers.set(LAYERS.ENTIRE_SCENE)
    finalComposer.render()
  }

  function resize() {
    const side = Math.max(1, Math.round(canvas.clientWidth))
    const dpr = window.devicePixelRatio
    renderer.setPixelRatio(dpr)
    renderer.setSize(side, side, false)
    camera.aspect = 1
    camera.updateProjectionMatrix()
    for (const composer of [torusComposer, bloomComposer, finalComposer]) {
      composer.setPixelRatio(dpr)
      composer.setSize(side, side)
    }
    // Points shrink with the canvas, but less than linearly: at a strictly
    // proportional size they fall under 3 px and the soft glow turns into
    // speckle. The square root keeps them overlapping into plasma.
    const ratio = side / REFERENCE_HEIGHT
    // gl_PointSize is in device pixels: scale by density so the orb looks
    // the same on a phone's high-density screen as on a desktop monitor.
    uniforms.uSize.value = CONFIG.pointSize * Math.sqrt(ratio) * Math.min(dpr, 2)
    opacityScale = Math.sqrt(ratio)
    motes.mat.uniforms.uRes.value.set(side * dpr, side * dpr)
    if (still) draw()
  }
  const observer = new ResizeObserver(resize)
  observer.observe(canvas)
  resize()

  let frame = 0
  function loop() {
    diveSmooth = Lerp(diveSmooth, mood.dive, 0.1)
    diveCurrent = Lerp(diveCurrent, diveSmooth, 0.06)
    presence = Lerp(presence, mood.presence, 0.08)
    voice = Lerp(voice, clamp(level(), 0, 1), 0.25)
    draw()
    frame = requestAnimationFrame(loop)
  }
  if (still) draw()
  else loop()

  return {
    setMood(next) {
      mood = next
      if (still) {
        diveSmooth = diveCurrent = next.dive
        presence = next.presence
        draw()
      }
    },
    dispose() {
      cancelAnimationFrame(frame)
      observer.disconnect()
      geometry.dispose()
      material.dispose()
      motes.geo.dispose()
      motes.mat.dispose()
      for (const composer of [torusComposer, bloomComposer, finalComposer]) {
        composer.renderTarget1.dispose()
        composer.renderTarget2.dispose()
      }
      renderer.dispose()
    },
  }
}
