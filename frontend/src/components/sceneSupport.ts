/**
 * The WebGL scenes (background field and presence orb) are off in automated
 * browsers: drawing them on a software renderer makes every end-to-end test
 * slow. ?bg turns them on there; ?nobg turns them off anywhere.
 */
export function sceneDisabled(): boolean {
  const params = new URLSearchParams(window.location.search)
  if (params.has('nobg')) return true
  return navigator.webdriver === true && !params.has('bg')
}
