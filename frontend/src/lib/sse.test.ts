import { describe, expect, test } from 'vitest'
import { parseSseChunk } from './sse'

describe('parseSseChunk', () => {
  test('parses complete events and keeps the remainder', () => {
    const buffer =
      'event: run.updated\ndata: {"run_id":3}\n\n: keepalive\n\nevent: policy.fired\ndata: {"run'
    const { events, rest } = parseSseChunk(buffer)
    expect(events).toEqual([{ type: 'run.updated', data: { run_id: 3 } }])
    expect(rest).toBe('event: policy.fired\ndata: {"run')
  })

  test('skips comment-only blocks', () => {
    const { events, rest } = parseSseChunk(': connected\n\n: keepalive\n\n')
    expect(events).toEqual([])
    expect(rest).toBe('')
  })

  test('drops malformed payloads without throwing', () => {
    const { events } = parseSseChunk('event: run.updated\ndata: {nope\n\n')
    expect(events).toEqual([])
  })

  test('parses several events in one chunk', () => {
    const buffer =
      'event: a\ndata: {"x":1}\n\nevent: b\ndata: {"y":2}\n\n'
    const { events } = parseSseChunk(buffer)
    expect(events).toHaveLength(2)
  })
})
