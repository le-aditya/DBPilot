/**
 * Exporting the diagram. PRD F4.
 *
 * The diagram is real SVG rather than positioned HTML, which is why SVG export
 * is a serialisation rather than a screenshot, and why the PNG is drawn from
 * that same serialisation instead of from a second rendering path that could
 * disagree with what is on screen.
 */

/** Inline the computed colours, because a detached SVG has no stylesheet. */
function serialise(svg: SVGSVGElement): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

  const source = svg.querySelectorAll('*')
  const target = copy.querySelectorAll('*')
  target.forEach((element, index) => {
    const computed = window.getComputedStyle(source[index])
    const fill = computed.fill
    const stroke = computed.stroke
    const color = computed.color
    if (fill && fill !== 'none') element.setAttribute('fill', fill)
    if (stroke && stroke !== 'none') element.setAttribute('stroke', stroke)
    if (element.tagName === 'text' && color) element.setAttribute('fill', color)
    element.removeAttribute('class')
  })
  copy.removeAttribute('class')

  return new XMLSerializer().serializeToString(copy)
}

export function toSvgBlob(svg: SVGSVGElement): Blob {
  return new Blob([serialise(svg)], { type: 'image/svg+xml;charset=utf-8' })
}

export async function toPngBlob(
  svg: SVGSVGElement,
  scale = 2,
): Promise<Blob> {
  const markup = serialise(svg)
  const width = Number(svg.getAttribute('width')) || svg.clientWidth || 1200
  const height = Number(svg.getAttribute('height')) || svg.clientHeight || 800

  const url = URL.createObjectURL(
    new Blob([markup], { type: 'image/svg+xml;charset=utf-8' }),
  )
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('The diagram could not be rendered.'))
      image.src = url
    })

    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const context = canvas.getContext('2d')
    if (!context) throw new Error('This browser cannot export a PNG.')
    context.scale(scale, scale)
    context.drawImage(image, 0, 0)

    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) =>
          blob ? resolve(blob) : reject(new Error('The PNG could not be created.')),
        'image/png',
      )
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
