// Measure an element's content box so SVG instruments render at true pixel
// size instead of stretching a fixed viewBox (which scales fonts grotesquely
// on large screens).

import { useEffect, useRef, useState } from 'react'

export function useMeasure<T extends HTMLElement>(fallbackWidth = 640, fallbackHeight = 320) {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: fallbackWidth, height: fallbackHeight })

  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect
      if (rect && rect.width > 0) {
        setSize({ width: rect.width, height: rect.height })
      }
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return { ref, width: size.width, height: size.height }
}
