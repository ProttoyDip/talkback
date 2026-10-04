/*
 * "Flow Wave": the animated background. A sea of glowing particle hills in
 * dark emerald, ported from the supplied Three.js scene with its constants,
 * shaders and postprocessing unchanged. Differences from the original page:
 *  - It lives behind the app instead of owning the page, so there is no
 *    scroll host. The scroll value (0..1) that dives the camera is set by the
 *    app from the conversation state (setScroll).
 *  - It can render a single still frame (reduced motion) and be disposed.
 */
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { CopyShader } from 'three/examples/jsm/shaders/CopyShader.js'
import { GammaCorrectionShader } from 'three/examples/jsm/shaders/GammaCorrectionShader.js'

const bgColor = '#02160c'
const flameColor = '#0aff7f'
const flameColor2 = '#aef0c0'
const flameAmt = 0.2
const atmoColor = '#7affbf'
const atmoCount = 300
const atmoSize = 24
const atmoSpeed = 1.0
const colorLow = '#02160c'
const colorHigh = '#34e89a'
const opacity = 0.26
const pointSize = 5.5
const brightness = 0.45
const waveHeight = 3
const flow = 1
const tilt = 0
const scale = 0.275
const scrollRise = 1.0
const camStartY = 7
const camStartZ = 16
const camEndY = 0.8
const camEndZ = -2
const lookStartZ = 2
const lookEndZ = -16
const parallax = 1.2
const pointerRadius = 7.0
const pointerStrength = 0.9

const LAYERS = { NONE: 0, TORUS_SCENE: 1, BLOOM_SCENE: 2, ENTIRE_SCENE: 3 }

const Lerp = (a: number, b: number, t: number) => a + (b - a) * t
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

function hexToVec3(hex: string) {
  const n = parseInt(hex.slice(1), 16)
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255)
}

const SNOISE = /* glsl */ `
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0); const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy)); vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz); vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy); vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + 1.0 * C.xxx; vec3 x2 = x0 - i2 + 2.0 * C.xxx; vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;
  i = mod(i, 289.0);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 1.0/7.0; vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z *ns.z);
  vec4 x_ = floor(j * ns.z); vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ *ns.x + ns.yyyy; vec4 y = y_ *ns.x + ns.yyyy; vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy); vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0; vec4 s1 = floor(b1)*2.0 + 1.0; vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy; vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy,h.x); vec3 p1 = vec3(a0.zw,h.y); vec3 p2 = vec3(a1.xy,h.z); vec3 p3 = vec3(a1.zw,h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.5 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0); m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}
`

const POINTS_VERTEX = /* glsl */ `
uniform float uTime; uniform float uStream; uniform float uSize; uniform float uWaveHeight; uniform float uFlow; uniform float uScale;
uniform vec3 uColLow; uniform vec3 uColHigh;
uniform vec3 uCursor; uniform float uRepelRadius; uniform float uRepelStrength; uniform float uActivity;
varying float vFade; varying vec3 vColor;
${SNOISE}
void main() {
  vec3 wp = vec3(position.x * 13.0, 0.0, position.z * 25.0);
  wp.x += position.y * 6.0;
  // uStream slides the sampled hills toward the camera (forward flight).
  float zc = wp.z + uStream;
  float wn = snoise(vec3(wp.x * 0.08, zc * 0.08, uTime * 0.15 * uFlow)) * 2.0;
  wn += snoise(vec3(wp.x * 0.16, zc * 0.16, uTime * 0.3 * uFlow)) * 0.8;
  wp.y += wn * uWaveHeight;

  vec3 finalPos = wp * uScale;
  vec4 modelPosition = modelMatrix * vec4(finalPos, 1.0);
  vec3 toP = modelPosition.xyz - uCursor;
  float cd = length(toP);
  float fall = smoothstep(uRepelRadius, 0.0, cd);
  modelPosition.xyz += normalize(toP + vec3(0.0001)) * fall * uRepelStrength * uActivity;
  vec4 mvPosition = viewMatrix * modelPosition;

  float colMix = smoothstep(-3.0, 3.0, position.y + position.x * 0.5);
  vColor = mix(uColLow, uColHigh, clamp(colMix, 0.0, 1.0));
  vFade = 1.0;

  gl_PointSize = uSize * (10.0 / -mvPosition.z);
  gl_PointSize = max(gl_PointSize, 1.5);
  gl_Position = projectionMatrix * mvPosition;
}
`

const POINTS_FRAGMENT = /* glsl */ `
uniform float uOpacity; uniform float uBrightness; uniform float uAppear;
varying float vFade; varying vec3 vColor;
void main() {
  vec2 xy = gl_PointCoord - 0.5;
  float ll = length(xy);
  if (ll > 0.5) discard;
  float a = smoothstep(0.5, 0.1, ll);
  gl_FragColor = vec4(vColor * uBrightness, vFade * a * uOpacity * uAppear);
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

export interface FlowScene {
  /** 0..1: how far the camera has dived into the field. Smoothed inside. */
  setScroll: (value: number) => void
  dispose: () => void
}

/**
 * Starts the scene on `canvas`. With `still` it draws one frame and stops
 * (reduced motion). Returns null when WebGL is not available.
 */
export function createFlowScene(canvas: HTMLCanvasElement, still: boolean): FlowScene | null {
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

  const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 400)
  camera.position.set(0, 7, 16)
  camera.layers.enable(LAYERS.TORUS_SCENE)
  camera.layers.enable(LAYERS.BLOOM_SCENE)
  camera.layers.enable(LAYERS.ENTIRE_SCENE)
  scene.add(camera)

  // The sphere is reshaped entirely in the vertex shader into a flat noise sheet.
  const geometry = new THREE.SphereGeometry(4.2, 200, 600)
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uStream: { value: 0 },
      uAppear: { value: 0 },
      uColLow: { value: hexToVec3(colorLow) },
      uColHigh: { value: hexToVec3(colorHigh) },
      uOpacity: { value: opacity },
      uSize: { value: pointSize },
      uBrightness: { value: brightness },
      uWaveHeight: { value: waveHeight },
      uFlow: { value: flow },
      uScale: { value: scale },
      uCursor: { value: new THREE.Vector3() },
      uRepelRadius: { value: pointerRadius },
      uRepelStrength: { value: pointerStrength },
      uActivity: { value: 0 },
    },
    vertexShader: POINTS_VERTEX,
    fragmentShader: POINTS_FRAGMENT,
  })
  const points = new THREE.Points(geometry, material)
  points.frustumCulled = false
  points.layers.enable(LAYERS.ENTIRE_SCENE)
  const group = new THREE.Group()
  group.add(points)
  scene.add(group)

  // Ambient motes that follow the camera.
  const motes = (() => {
    const n = Math.round(atmoCount)
    const positions = new Float32Array(n * 3)
    const sizes = new Float32Array(n)
    const seeds = new Float32Array(n)
    for (let i = 0; i < n; i++) {
      positions[i * 3] = 2 * Math.random() - 1
      positions[i * 3 + 1] = 2 * Math.random() - 1
      positions[i * 3 + 2] = 2 * Math.random() - 1
      sizes[i] = atmoSize * (0.4 + Math.random())
      seeds[i] = Math.random()
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    geo.setAttribute('seed', new THREE.BufferAttribute(seeds, 1))
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: false,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: hexToVec3(atmoColor) },
        uRes: { value: new THREE.Vector2(window.innerWidth * window.devicePixelRatio, window.innerHeight * window.devicePixelRatio) },
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
  const size = new THREE.Vector2(window.innerWidth, window.innerHeight)
  const renderPass = new RenderPass(scene, camera)

  const torusComposer = new EffectComposer(renderer)
  torusComposer.renderToScreen = false
  torusComposer.addPass(renderPass)
  torusComposer.addPass(new ShaderPass(GammaCorrectionShader))
  torusComposer.addPass(new UnrealBloomPass(size.clone(), 0.22, 0.2, 0))
  torusComposer.addPass(new ShaderPass(CopyShader))

  const bloomComposer = new EffectComposer(renderer)
  bloomComposer.renderToScreen = false
  bloomComposer.addPass(renderPass)
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
        uBg: { value: hexToVec3(bgColor) },
        uFlameA: { value: hexToVec3(flameColor) },
        uFlameB: { value: hexToVec3(flameColor2) },
        uFlameAmt: { value: flameAmt },
      },
      vertexShader: FINAL_VERTEX,
      fragmentShader: FINAL_FRAGMENT,
    }),
  )
  const finalComposer = new EffectComposer(renderer)
  finalComposer.addPass(renderPass)
  finalComposer.addPass(finalPass)
  finalPass.uniforms.bloomTexture.value = bloomComposer.renderTarget1.texture
  finalPass.uniforms.torusTexture.value = torusComposer.renderTarget1.texture

  // Input
  let scrollTarget = 0
  let scrollSmooth = 0
  let scrollCurrent = 0
  const mouseTarget = { x: 0, y: 0 }
  const mouse = { x: 0, y: 0 }
  const pointer = { world: new THREE.Vector3(), activity: 0, active: false, lastMove: performance.now() }

  const onMouseMove = (e: MouseEvent) => {
    mouseTarget.x = (e.clientX / window.innerWidth) * 2 - 1
    mouseTarget.y = -((e.clientY / window.innerHeight) * 2 - 1)
    pointer.active = true
    pointer.lastMove = performance.now()
  }
  const onMouseOut = () => {
    pointer.active = false
  }
  window.addEventListener('mousemove', onMouseMove, { passive: true })
  window.addEventListener('mouseout', onMouseOut)

  const ndc = new THREE.Vector3()
  const dir = new THREE.Vector3()
  const target = new THREE.Vector3()
  function updatePointerWorld() {
    target.set(0, 0, 0)
    if (pointer.active) {
      ndc.set(mouse.x, mouse.y, 0.5).unproject(camera)
      dir.copy(ndc).sub(camera.position).normalize()
      const dn = dir.z
      if (Math.abs(dn) > 1e-4) {
        const tt = -camera.position.z / dn
        if (tt > 0 && Number.isFinite(tt)) target.copy(camera.position).addScaledVector(dir, tt)
      }
    }
    pointer.world.lerp(target, 0.12)
    const idle = (performance.now() - pointer.lastMove) / 1000
    pointer.activity += ((pointer.active && idle < 3 ? 1 : 0) - pointer.activity) * 0.06
  }

  // Scene update
  const uniforms = material.uniforms
  let stream = 0
  let t0 = performance.now() / 1000
  const appearStart = performance.now()

  function update(scroll: number, m: { x: number; y: number }) {
    const t = performance.now() / 1000
    const dt = Math.min(0.05, t - t0)
    t0 = t
    uniforms.uTime.value = t

    // Stream the hills toward us at a constant rate; grow the swell with scroll.
    stream += dt * (flow * 2.0) * 4.0
    uniforms.uStream.value = stream
    uniforms.uWaveHeight.value = waveHeight * (1 + scroll * scrollRise)

    // Camera fly-path: smoothstep over the first 35% of scroll.
    const ea = Math.min(scroll / 0.35, 1.0)
    const e = ea * ea * (3 - 2 * ea)
    const camY = Lerp(camStartY, camEndY, e)
    const camZ = Lerp(camStartZ, camEndZ, e)
    camera.position.set(m.x * parallax, camY + m.y * parallax * 0.3, camZ)
    camera.lookAt(m.x * parallax * 0.5, Lerp(0.0, 0.6, e), Lerp(lookStartZ, lookEndZ, e))
    group.rotation.x = -tilt
    group.rotation.y = 0
    updatePointerWorld()

    uniforms.uCursor.value.copy(pointer.world)
    uniforms.uActivity.value = pointer.activity
    const elapsed = (performance.now() - appearStart) / 1000
    uniforms.uAppear.value = still ? 1 : Math.max(0, Math.min(1, (elapsed - 0.2) / 1.4))

    // Motes follow the camera; the same clock drives the corner flames.
    motes.mat.uniforms.uTime.value = t * atmoSpeed * 8.0
    motes.pts.position.copy(camera.position)
    finalPass.uniforms.iTime.value = t
  }

  function draw() {
    update(scrollCurrent, mouse)
    camera.layers.set(LAYERS.TORUS_SCENE)
    torusComposer.render()
    camera.layers.set(LAYERS.BLOOM_SCENE)
    bloomComposer.render()
    camera.layers.set(LAYERS.ENTIRE_SCENE)
    finalComposer.render()
  }

  function resize() {
    const w = window.innerWidth
    const h = window.innerHeight
    const dpr = window.devicePixelRatio
    renderer.setPixelRatio(dpr)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    for (const composer of [torusComposer, bloomComposer, finalComposer]) {
      composer.setPixelRatio(dpr)
      composer.setSize(w, h)
    }
    motes.mat.uniforms.uRes.value.set(w * dpr, h * dpr)
    if (still) draw()
  }
  window.addEventListener('resize', resize)
  resize()

  let frame = 0
  function loop() {
    scrollSmooth = Lerp(scrollSmooth, scrollTarget, 0.1)
    scrollCurrent = Lerp(scrollCurrent, scrollSmooth, 0.06)
    mouse.x = Lerp(mouse.x, mouseTarget.x, 0.06)
    mouse.y = Lerp(mouse.y, mouseTarget.y, 0.06)
    draw()
    frame = requestAnimationFrame(loop)
  }
  if (still) draw()
  else loop()

  return {
    setScroll(value) {
      scrollTarget = clamp(value, 0, 1)
      if (still) {
        scrollSmooth = scrollCurrent = scrollTarget
        draw()
      }
    },
    dispose() {
      cancelAnimationFrame(frame)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseout', onMouseOut)
      window.removeEventListener('resize', resize)
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
