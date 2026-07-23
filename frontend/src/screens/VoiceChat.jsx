import { useEffect, useRef, useState } from 'react'
import { voiceWsUrl } from '../api.js'

// Family Phone: free-form voice calls between players, unlocked at Level 5.
// The backend only relays call setup (who's calling whom + WebRTC handshake);
// the audio itself streams directly between the two browsers.

const RTC_CONFIG = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] }

export default function VoiceChat({ player, onBack }) {
  const unlockLevel = 5
  const locked = player.level.num < unlockLevel

  const [online, setOnline] = useState([])
  const [call, setCall] = useState(null) // {peerId, peerName, state: calling|ringing|live}
  const [muted, setMuted] = useState(false)
  const [notice, setNotice] = useState('')

  const wsRef = useRef(null)
  const pcRef = useRef(null)
  const streamRef = useRef(null)
  const audioRef = useRef(null)
  const pendingIce = useRef([])
  const callRef = useRef(null)
  callRef.current = call

  const send = (msg) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }

  const teardown = () => {
    pcRef.current?.close()
    pcRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    pendingIce.current = []
    setMuted(false)
    setCall(null)
  }

  const hangUp = (tellPeer = true) => {
    const c = callRef.current
    if (tellPeer && c) send({ type: 'hangup', to: c.peerId })
    teardown()
  }

  // Build the peer connection; the caller creates the offer, the callee
  // answers when it arrives (see the 'signal' handler below).
  const startPeer = async (peerId, isCaller) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    const pc = new RTCPeerConnection(RTC_CONFIG)
    pcRef.current = pc
    stream.getTracks().forEach((t) => pc.addTrack(t, stream))
    pc.ontrack = (e) => {
      if (audioRef.current) audioRef.current.srcObject = e.streams[0]
      setCall((c) => (c ? { ...c, state: 'live' } : c))
    }
    pc.onicecandidate = (e) => {
      if (e.candidate) send({ type: 'signal', to: peerId, data: { candidate: e.candidate } })
    }
    pc.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) hangUp(false)
    }
    if (isCaller) {
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      send({ type: 'signal', to: peerId, data: { sdp: pc.localDescription } })
    }
  }

  const handleSignal = async (msg) => {
    const pc = pcRef.current
    if (!pc) return
    const { sdp, candidate } = msg.data || {}
    if (sdp) {
      await pc.setRemoteDescription(sdp)
      for (const c of pendingIce.current) await pc.addIceCandidate(c)
      pendingIce.current = []
      if (sdp.type === 'offer') {
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        send({ type: 'signal', to: msg.from, data: { sdp: pc.localDescription } })
      }
    } else if (candidate) {
      if (pc.remoteDescription) await pc.addIceCandidate(candidate)
      else pendingIce.current.push(candidate)
    }
  }

  useEffect(() => {
    if (locked) return undefined
    const ws = new WebSocket(voiceWsUrl())
    wsRef.current = ws
    ws.onmessage = async (e) => {
      let msg
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      const c = callRef.current
      if (msg.type === 'roster') {
        setOnline(msg.online.filter((o) => o.id !== player.id))
      } else if (msg.type === 'call') {
        if (c) send({ type: 'decline', to: msg.from }) // busy
        else setCall({ peerId: msg.from, peerName: msg.from_name, state: 'ringing' })
      } else if (msg.type === 'accept' && c?.peerId === msg.from) {
        await startPeer(msg.from, true)
      } else if (msg.type === 'decline' && c?.peerId === msg.from) {
        teardown()
        setNotice(`${msg.from_name} can't talk right now.`)
      } else if (msg.type === 'signal' && c?.peerId === msg.from) {
        await handleSignal(msg)
      } else if (msg.type === 'hangup' && c?.peerId === msg.from) {
        teardown()
      } else if (msg.type === 'peer-offline' && c?.peerId === msg.to) {
        teardown()
        setNotice('They just went offline.')
      }
    }
    ws.onclose = () => teardown()
    return () => {
      hangUp(true)
      ws.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked, player.id])

  const placeCall = (peer) => {
    setNotice('')
    setCall({ peerId: peer.id, peerName: peer.name, state: 'calling' })
    send({ type: 'call', to: peer.id })
  }

  const acceptCall = async () => {
    const c = callRef.current
    if (!c) return
    await startPeer(c.peerId, false) // be ready before the offer arrives
    send({ type: 'accept', to: c.peerId })
    setCall({ ...c, state: 'connecting' })
  }

  const declineCall = () => {
    const c = callRef.current
    if (c) send({ type: 'decline', to: c.peerId })
    teardown()
  }

  const toggleMute = () => {
    const stream = streamRef.current
    if (!stream) return
    const next = !muted
    stream.getAudioTracks().forEach((t) => {
      t.enabled = !next
    })
    setMuted(next)
  }

  if (locked)
    return (
      <div className="shell center">
        <div className="card">
          <h2>📞 Family Phone</h2>
          <p className="phone-locked">
            🔒 Unlocks at <strong>Level {unlockLevel}</strong>. You're Level{' '}
            {player.level.num} — keep questing and this phone is yours: real
            voice calls with the family, about anything you like!
          </p>
          <button className="btn primary big" onClick={onBack}>
            Back to camp 🏕️
          </button>
        </div>
      </div>
    )

  return (
    <div className="shell center">
      <div className="card">
        <h2>📞 Family Phone</h2>
        <audio ref={audioRef} autoPlay />
        {call?.state === 'ringing' ? (
          <div className="phone-panel">
            <p className="phone-status">
              📳 <strong>{call.peerName}</strong> is calling you!
            </p>
            <div className="row">
              <button className="btn ghost" onClick={declineCall}>
                Not now
              </button>
              <button className="btn primary grow" onClick={acceptCall}>
                Pick up 🎙️
              </button>
            </div>
          </div>
        ) : call ? (
          <div className="phone-panel">
            <p className="phone-status">
              {call.state === 'live' ? '🟢 Talking with' : '📞 Calling'}{' '}
              <strong>{call.peerName}</strong>
              {call.state !== 'live' && '…'}
            </p>
            <div className="row">
              <button className="btn ghost" onClick={toggleMute}>
                {muted ? '🔊 Unmute' : '🔇 Mute'}
              </button>
              <button className="btn primary grow" onClick={() => hangUp(true)}>
                Hang up 👋
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="muted">
              Free-form voice calls — talk about anything! Whoever you call
              hears a ring and chooses whether to pick up.
            </p>
            {notice && <p className="phone-notice">{notice}</p>}
            {online.length === 0 ? (
              <p className="phone-empty">
                Nobody else is by the phone right now. Ask a family member to
                open their Family Phone screen!
              </p>
            ) : (
              <div className="stack">
                {online.map((o) => (
                  <button key={o.id} className="btn big" onClick={() => placeCall(o)}>
                    📱 Call {o.name}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        <button className="btn ghost big" onClick={onBack}>
          Back to camp 🏕️
        </button>
      </div>
    </div>
  )
}
