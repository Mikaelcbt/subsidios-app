import { useEffect, useRef, useState } from 'react'

interface Documento {
  id: string
  nome: string
  tamanho: number
  parece_fatura: boolean
  corrompido: boolean
}

interface Fatura {
  id: string
  nome: string
  tamanho: number
  paginas: number
  data: string | null
  erro: string | null
}

interface ItemSubir {
  id: string
  nome: string
  tamanho: number
  tipo: 'documento' | 'faturas'
}

interface Destino {
  drive: string
  letra: string
  pasta_processo: string
  subpasta: string
  caminho: string
  pasta_existe: boolean
  subsidios_existe: boolean
  url: string | null
  avisos: string[]
}

interface EnvioDados {
  envio_id: string
  documentos: Documento[]
  faturas: Fatura[]
  ordem_faturas: 'data' | 'nome' | 'manual'
  faturas_pdf: { nome: string; paginas: number; tamanho: number } | null
  itens_para_subir: ItemSubir[]
  destino: Destino | null
}

type StatusItem =
  | { s: 'pendente' }
  | { s: 'enviando' }
  | { s: 'enviado' }
  | { s: 'ja_existia' }
  | { s: 'erro'; msg: string }

export interface DriveStatus {
  configurado: boolean
  modo: string | null
  conta?: string | null
  faixas: { nome: string; de: string; ate: string }[]
  erro: string | null
}

const PARALELO = 3

function tamanhoFmt(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function dataFmt(iso: string | null) {
  if (!iso) return 'sem data'
  const [a, m, d] = iso.split('-')
  return d === '01' ? `${m}/${a}` : `${d}/${m}/${a}`
}

async function lerErro(res: Response, padrao: string) {
  try {
    const j = await res.json()
    return j.detail || padrao
  } catch {
    return padrao
  }
}

export function EnvioDrive({ token, driveStatus }: { token: string; driveStatus: DriveStatus | null }) {
  const [autor, setAutor] = useState('')
  const [processo, setProcesso] = useState('')
  const [envio, setEnvio] = useState<EnvioDados | null>(null)
  const [faturasPendentes, setFaturasPendentes] = useState<File[]>([])
  const [carregandoDocs, setCarregandoDocs] = useState(false)
  const [juntando, setJuntando] = useState(false)
  const [destino, setDestino] = useState<Destino | null>(null)
  const [destinoErro, setDestinoErro] = useState('')
  const [buscandoDestino, setBuscandoDestino] = useState(false)
  const [status, setStatus] = useState<Record<string, StatusItem>>({})
  const [subindo, setSubindo] = useState(false)
  const [pastaUrl, setPastaUrl] = useState<string | null>(null)
  const [erro, setErro] = useState('')
  const envioRef = useRef<EnvioDados | null>(null)
  envioRef.current = envio

  const headers = { Authorization: `Bearer ${token}` }

  // ---------- destino (prévia de onde vai salvar) ----------
  useEffect(() => {
    setDestino(null)
    setDestinoErro('')
    if (!autor.trim() || processo.replace(/\D/g, '').length < 7 || !driveStatus?.configurado) return
    const t = setTimeout(async () => {
      setBuscandoDestino(true)
      try {
        const qs = new URLSearchParams({ autor: autor.trim(), processo: processo.trim() })
        const res = await fetch(`/api/envios/destino?${qs}`, { headers })
        if (res.ok) setDestino(await res.json())
        else setDestinoErro(await lerErro(res, 'Não consegui ver a pasta no Drive.'))
      } catch {
        setDestinoErro('Não consegui falar com o servidor.')
      } finally {
        setBuscandoDestino(false)
      }
    }, 700)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autor, processo, driveStatus?.configurado])

  // ---------- envio ----------
  const garantirEnvio = async (): Promise<string> => {
    if (envioRef.current) return envioRef.current.envio_id
    const res = await fetch('/api/envios', { method: 'POST', headers })
    if (!res.ok) throw new Error(await lerErro(res, 'Não consegui iniciar o envio.'))
    const data: EnvioDados = await res.json()
    setEnvio(data)
    envioRef.current = data
    return data.envio_id
  }

  const atualizar = (data: EnvioDados) => {
    setEnvio(data)
    // Qualquer mudança nos arquivos zera o status de envio dos itens que mudaram
    setStatus(prev => {
      const novo: Record<string, StatusItem> = {}
      for (const it of data.itens_para_subir) {
        if (it.id !== 'faturas' && prev[it.id]) novo[it.id] = prev[it.id]
      }
      return novo
    })
  }

  const enviarDocumentos = async (files: File[]) => {
    if (!files.length) return
    setErro('')
    setCarregandoDocs(true)
    try {
      const id = await garantirEnvio()
      const fd = new FormData()
      files.forEach(f => fd.append('arquivos', f))
      const res = await fetch(`/api/envios/${id}/documentos`, { method: 'POST', headers, body: fd })
      if (!res.ok) throw new Error(await lerErro(res, 'Erro ao receber os documentos.'))
      atualizar(await res.json())
    } catch (e: any) {
      setErro(e.message)
    } finally {
      setCarregandoDocs(false)
    }
  }

  const removerDocumento = async (docId: string) => {
    if (!envio) return
    const res = await fetch(`/api/envios/${envio.envio_id}/documentos/${docId}`, { method: 'DELETE', headers })
    if (res.ok) atualizar(await res.json())
  }

  const moverParaFaturas = async (ids: string[]) => {
    if (!envio) return
    setJuntando(true)
    try {
      const res = await fetch(`/api/envios/${envio.envio_id}/documentos/mover-faturas`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      })
      if (res.ok) atualizar(await res.json())
    } finally {
      setJuntando(false)
    }
  }

  const juntarFaturas = async () => {
    if (!faturasPendentes.length) return
    setErro('')
    setJuntando(true)
    try {
      const id = await garantirEnvio()
      const fd = new FormData()
      faturasPendentes.forEach(f => fd.append('arquivos', f))
      const res = await fetch(`/api/envios/${id}/faturas`, { method: 'POST', headers, body: fd })
      if (!res.ok) throw new Error(await lerErro(res, 'Erro ao juntar as faturas.'))
      atualizar(await res.json())
      setFaturasPendentes([])
    } catch (e: any) {
      setErro(e.message)
    } finally {
      setJuntando(false)
    }
  }

  const ordenar = async (modo: 'data' | 'nome' | 'manual', ids?: string[]) => {
    if (!envio) return
    setJuntando(true)
    try {
      const res = await fetch(`/api/envios/${envio.envio_id}/faturas/ordem`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ modo, ids }),
      })
      if (res.ok) atualizar(await res.json())
      else setErro(await lerErro(res, 'Erro ao reordenar.'))
    } finally {
      setJuntando(false)
    }
  }

  const mover = (idx: number, delta: number) => {
    if (!envio) return
    const ids = envio.faturas.map(f => f.id)
    const alvo = idx + delta
    if (alvo < 0 || alvo >= ids.length) return
    ;[ids[idx], ids[alvo]] = [ids[alvo], ids[idx]]
    ordenar('manual', ids)
  }

  const removerFatura = async (fid: string) => {
    if (!envio) return
    setJuntando(true)
    try {
      const res = await fetch(`/api/envios/${envio.envio_id}/faturas/${fid}`, { method: 'DELETE', headers })
      if (res.ok) atualizar(await res.json())
    } finally {
      setJuntando(false)
    }
  }

  const verPdf = async () => {
    if (!envio) return
    const janela = window.open('', '_blank')
    const res = await fetch(`/api/envios/${envio.envio_id}/faturas.pdf`, { headers })
    if (!res.ok) {
      janela?.close()
      setErro('Não consegui abrir o PDF.')
      return
    }
    const url = URL.createObjectURL(await res.blob())
    if (janela) janela.location.href = url
    else window.location.href = url
  }

  // ---------- subir pro Drive ----------
  const subir = async (somenteIds?: string[]) => {
    if (!envio) return
    setErro('')
    setSubindo(true)
    try {
      const res = await fetch(`/api/envios/${envio.envio_id}/pasta`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ autor: autor.trim(), processo: processo.trim() }),
      })
      if (!res.ok) throw new Error(await lerErro(res, 'Não consegui criar a pasta no Drive.'))
      const data: EnvioDados = await res.json()
      setEnvio(data)
      setPastaUrl(data.destino?.url ?? null)

      const fila = data.itens_para_subir.filter(it => !somenteIds || somenteIds.includes(it.id))
      setStatus(prev => {
        const n = { ...prev }
        fila.forEach(it => (n[it.id] = { s: 'pendente' }))
        return n
      })

      let cursor = 0
      const worker = async () => {
        while (cursor < fila.length) {
          const it = fila[cursor++]
          setStatus(prev => ({ ...prev, [it.id]: { s: 'enviando' } }))
          try {
            const r = await fetch(`/api/envios/${data.envio_id}/itens/${it.id}/subir`, { method: 'POST', headers })
            if (!r.ok) throw new Error(await lerErro(r, 'Falhou'))
            const j = await r.json()
            setStatus(prev => ({ ...prev, [it.id]: { s: j.status } }))
          } catch (e: any) {
            setStatus(prev => ({ ...prev, [it.id]: { s: 'erro', msg: e.message || 'Falhou' } }))
          }
        }
      }
      await Promise.all(Array.from({ length: Math.min(PARALELO, fila.length) }, worker))
    } catch (e: any) {
      setErro(e.message)
    } finally {
      setSubindo(false)
    }
  }

  const novoEnvio = () => {
    setAutor('')
    setProcesso('')
    setEnvio(null)
    setFaturasPendentes([])
    setStatus({})
    setPastaUrl(null)
    setErro('')
  }

  // ---------- derivados ----------
  const itens = envio?.itens_para_subir ?? []
  const falhas = itens.filter(it => status[it.id]?.s === 'erro')
  const concluidos = itens.filter(it => ['enviado', 'ja_existia'].includes(status[it.id]?.s ?? ''))
  const tudoEnviado = itens.length > 0 && concluidos.length === itens.length
  const suspeitas = envio?.documentos.filter(d => d.parece_fatura) ?? []
  // Depois que FATURAS.pdf subiu, travar a ordem pra não ficar diferente do que está no Drive
  const faturasTravadas = juntando || subindo || !!status['faturas']
  const podeSubir =
    !!autor.trim() && !!processo.trim() && itens.length > 0 && !subindo && !juntando &&
    !carregandoDocs && faturasPendentes.length === 0 && !!driveStatus?.configurado

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Enviar subsídios pro Drive</h2>
        <p className="text-gray-500 mt-1">
          Cria a pasta do processo na letra certa, a subpasta SUBSÍDIOS, e sobe tudo solto com as faturas num PDF só.
        </p>
      </div>

      {driveStatus && !driveStatus.configurado && (
        <Aviso cor="amber">
          O Drive do escritório ainda não foi configurado no servidor. Dá pra preparar os arquivos, mas o botão de subir
          só funciona depois da configuração.
        </Aviso>
      )}
      {driveStatus?.erro && <Aviso cor="red">{driveStatus.erro}</Aviso>}

      {/* 1. Dados */}
      <Secao numero={1} titulo="Dados do processo">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Campo label="Nome do autor" valor={autor} setValor={setAutor} placeholder="Ex: TERESINHA DE JESUS MOURA" />
          <Campo label="Número do processo" valor={processo} setValor={setProcesso} placeholder="Ex: 0844498-70.2025.8.18.0140" />
        </div>
        <PreviaDestino destino={destino} erro={destinoErro} buscando={buscandoDestino} />
      </Secao>

      {/* 2. Documentos */}
      <Secao numero={2} titulo="Documentos e ZIPs do Pan">
        <p className="text-sm text-gray-500 -mt-2">
          Os ZIPs são abertos aqui e tudo vai solto pra SUBSÍDIOS, com o nome original.
        </p>
        <Dropzone
          id="docs-input"
          texto="Arraste os documentos e ZIPs aqui"
          subtexto="ZIP, PDF, imagens"
          accept=".zip,.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.txt"
          onFiles={enviarDocumentos}
          carregando={carregandoDocs}
        />
        {suspeitas.length > 0 && (
          <div className="flex items-center justify-between gap-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
            <span>
              {suspeitas.length === 1 ? '1 arquivo parece' : `${suspeitas.length} arquivos parecem`} fatura. Quer juntar
              no PDF de faturas em vez de subir solto?
            </span>
            <button
              onClick={() => moverParaFaturas(suspeitas.map(s => s.id))}
              className="shrink-0 bg-blue-600 text-white px-3 py-1.5 rounded-lg font-medium hover:bg-blue-700"
            >
              Mover pra faturas
            </button>
          </div>
        )}
        {envio && envio.documentos.length > 0 && (
          <ListaArquivos titulo={`${envio.documentos.length} arquivos prontos`}>
            {envio.documentos.map(d => (
              <LinhaArquivo
                key={d.id}
                nome={d.nome}
                detalhe={tamanhoFmt(d.tamanho)}
                alerta={d.corrompido ? 'ZIP corrompido, vai subir como está' : undefined}
                status={status[d.id]}
                onRemover={subindo ? undefined : () => removerDocumento(d.id)}
              />
            ))}
          </ListaArquivos>
        )}
      </Secao>

      {/* 3. Faturas */}
      <Secao numero={3} titulo="Faturas">
        <p className="text-sm text-gray-500 -mt-2">
          PDFs ou ZIP de faturas. Elas viram um arquivo só, FATURAS.pdf.
        </p>
        <Dropzone
          id="faturas-input"
          texto="Arraste as faturas aqui"
          subtexto="PDF ou ZIP"
          accept=".zip,.pdf"
          onFiles={files => setFaturasPendentes(prev => [...prev, ...files])}
          carregando={false}
        />
        {faturasPendentes.length > 0 && (
          <div className="space-y-2">
            <ListaArquivos titulo={`${faturasPendentes.length} arquivos para juntar`}>
              {faturasPendentes.map((f, i) => (
                <LinhaArquivo
                  key={i}
                  nome={f.name}
                  detalhe={tamanhoFmt(f.size)}
                  onRemover={() => setFaturasPendentes(prev => prev.filter((_, j) => j !== i))}
                />
              ))}
            </ListaArquivos>
            <button
              onClick={juntarFaturas}
              disabled={juntando}
              className="w-full bg-gray-900 text-white py-2.5 rounded-lg font-semibold hover:bg-gray-800 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {juntando && <Spinner />}
              {juntando ? 'Juntando...' : 'Juntar faturas'}
            </button>
          </div>
        )}

        {envio && envio.faturas.length > 0 && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200">
              <div>
                <p className="font-semibold text-gray-900 flex items-center gap-2">
                  FATURAS.pdf {juntando && <Spinner escuro />}
                </p>
                <p className="text-sm text-gray-500">
                  {envio.faturas_pdf
                    ? `${envio.faturas_pdf.paginas} páginas · ${envio.faturas.filter(f => !f.erro).length} faturas · ${tamanhoFmt(envio.faturas_pdf.tamanho)}`
                    : 'Nenhuma fatura válida'}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={envio.ordem_faturas}
                  onChange={e => ordenar(e.target.value as 'data' | 'nome')}
                  disabled={faturasTravadas}
                  className="text-sm px-2 py-1.5 border border-gray-300 rounded-lg bg-white"
                >
                  <option value="data">Ordem: data (mais antiga primeiro)</option>
                  <option value="nome">Ordem: nome do arquivo</option>
                  {envio.ordem_faturas === 'manual' && <option value="manual">Ordem: manual</option>}
                </select>
                {envio.faturas_pdf && (
                  <button
                    onClick={verPdf}
                    className="text-sm bg-white border border-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-50"
                  >
                    Ver PDF
                  </button>
                )}
              </div>
            </div>
            <ol className="divide-y divide-gray-100">
              {envio.faturas.map((f, i) => (
                <li key={f.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                  <span className="w-6 text-right text-gray-400 tabular-nums">{i + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className={`truncate ${f.erro ? 'text-gray-400 line-through' : 'text-gray-700'}`}>{f.nome}</p>
                    {f.erro && <p className="text-xs text-red-600">{f.erro}</p>}
                  </div>
                  <span className="text-xs text-gray-500 w-20 text-right">{dataFmt(f.data)}</span>
                  <span className="text-xs text-gray-400 w-14 text-right">{f.paginas} pág.</span>
                  <div className="flex items-center">
                    <BotaoIcone titulo="Subir" onClick={() => mover(i, -1)} disabled={faturasTravadas || i === 0}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                    </BotaoIcone>
                    <BotaoIcone titulo="Descer" onClick={() => mover(i, 1)} disabled={faturasTravadas || i === envio.faturas.length - 1}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </BotaoIcone>
                    <BotaoIcone titulo="Remover" onClick={() => removerFatura(f.id)} disabled={faturasTravadas}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </BotaoIcone>
                  </div>
                </li>
              ))}
            </ol>
            {envio.faturas_pdf && (
              <div className="px-4 py-2 border-t border-gray-100">
                <LinhaArquivo nome="FATURAS.pdf" detalhe="vai pra SUBSÍDIOS" status={status['faturas']} />
              </div>
            )}
          </div>
        )}
      </Secao>

      {/* 4. Subir */}
      <Secao numero={4} titulo="Subir para a pasta do processo">
        {destino ? (
          <p className="text-sm text-gray-700">
            Destino: <span className="font-mono text-gray-900">{destino.caminho}</span>
          </p>
        ) : (
          <p className="text-sm text-gray-500">Preencha autor e processo pra ver o destino.</p>
        )}

        {faturasPendentes.length > 0 && (
          <Aviso cor="amber">Tem faturas que ainda não foram juntadas. Clique em "Juntar faturas" antes de subir.</Aviso>
        )}
        {erro && <Aviso cor="red">{erro}</Aviso>}

        {Object.keys(status).length > 0 && (
          <div className="text-sm text-gray-700 bg-gray-50 rounded-lg px-4 py-3">
            {concluidos.length} de {itens.length} na pasta
            {falhas.length > 0 && <span className="text-red-600"> · {falhas.length} falharam</span>}
            {subindo && <span className="text-gray-500"> · enviando...</span>}
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          {falhas.length > 0 && !subindo ? (
            <button
              onClick={() => subir(falhas.map(f => f.id))}
              className="flex-1 bg-red-600 text-white py-3 px-6 rounded-xl font-semibold hover:bg-red-700"
            >
              Tentar de novo os {falhas.length} que falharam
            </button>
          ) : !tudoEnviado ? (
            <button
              onClick={() => subir()}
              disabled={!podeSubir}
              className="flex-1 bg-green-600 text-white py-3 px-6 rounded-xl font-semibold hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {subindo && <Spinner />}
              {subindo ? 'Subindo...' : `Subir ${itens.length || ''} arquivos para a pasta do processo`}
            </button>
          ) : null}

          {pastaUrl && (
            <a
              href={pastaUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white border border-gray-300 text-gray-700 py-3 px-6 rounded-xl font-semibold hover:bg-gray-50"
            >
              Abrir pasta no Drive
            </a>
          )}
          {tudoEnviado && (
            <button
              onClick={novoEnvio}
              className="bg-blue-600 text-white py-3 px-6 rounded-xl font-semibold hover:bg-blue-700"
            >
              Novo processo
            </button>
          )}
        </div>
      </Secao>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pedaços de tela
// ---------------------------------------------------------------------------

function Secao({ numero, titulo, children }: { numero: number; titulo: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
      <h3 className="font-semibold text-gray-900 flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center">{numero}</span>
        {titulo}
      </h3>
      {children}
    </div>
  )
}

function Campo({ label, valor, setValor, placeholder }: {
  label: string; valor: string; setValor: (v: string) => void; placeholder: string
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type="text"
        value={valor}
        onChange={e => setValor(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
      />
    </div>
  )
}

function PreviaDestino({ destino, erro, buscando }: { destino: Destino | null; erro: string; buscando: boolean }) {
  if (buscando) return <p className="text-sm text-gray-500 flex items-center gap-2"><Spinner escuro /> Procurando a pasta no Drive...</p>
  if (erro) return <Aviso cor="red">{erro}</Aviso>
  if (!destino) return null
  return (
    <div className="bg-gray-50 rounded-lg px-4 py-3 text-sm space-y-1">
      <p className="text-gray-700">
        <span className="text-gray-500">Drive:</span> {destino.drive} <span className="text-gray-400">›</span> {destino.letra}{' '}
        <span className="text-gray-400">›</span> <span className="font-medium">{destino.pasta_processo}</span>{' '}
        <span className="text-gray-400">›</span> {destino.subpasta}
      </p>
      <p className={destino.pasta_existe ? 'text-blue-700' : 'text-green-700'}>
        {destino.pasta_existe
          ? `A pasta do processo já existe, vou usar ela${destino.subsidios_existe ? ' e a SUBSÍDIOS que já está lá' : ' e criar a SUBSÍDIOS'}.`
          : 'Pasta nova: vou criar a pasta do processo e a SUBSÍDIOS.'}
      </p>
      {destino.avisos.map((a, i) => (
        <p key={i} className="text-amber-700">{a}</p>
      ))}
    </div>
  )
}

function Dropzone({ id, texto, subtexto, accept, onFiles, carregando }: {
  id: string; texto: string; subtexto: string; accept: string
  onFiles: (f: File[]) => void; carregando: boolean
}) {
  const [ativo, setAtivo] = useState(false)
  return (
    <div
      onDragOver={e => { e.preventDefault(); setAtivo(true) }}
      onDragLeave={() => setAtivo(false)}
      onDrop={e => { e.preventDefault(); setAtivo(false); onFiles(Array.from(e.dataTransfer.files)) }}
      onClick={() => !carregando && document.getElementById(id)?.click()}
      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
        ativo ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
      }`}
    >
      {carregando ? (
        <p className="text-gray-600 font-medium flex items-center justify-center gap-2"><Spinner escuro /> Abrindo os arquivos...</p>
      ) : (
        <>
          <p className="text-gray-600 font-medium">{texto}</p>
          <p className="text-sm text-gray-400 mt-1">ou clique para selecionar · {subtexto}</p>
        </>
      )}
      <input
        id={id}
        type="file"
        multiple
        accept={accept}
        className="hidden"
        onChange={e => {
          if (e.target.files) onFiles(Array.from(e.target.files))
          e.target.value = ''
        }}
      />
    </div>
  )
}

function ListaArquivos({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">{titulo}</p>
      <div className="space-y-1 max-h-80 overflow-y-auto">{children}</div>
    </div>
  )
}

function LinhaArquivo({ nome, detalhe, alerta, status, onRemover }: {
  nome: string; detalhe: string; alerta?: string; status?: StatusItem; onRemover?: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-1.5 bg-gray-50 rounded-lg">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-gray-700 truncate">{nome}</span>
          <span className="text-xs text-gray-400 shrink-0">{detalhe}</span>
        </div>
        {alerta && <p className="text-xs text-amber-700">{alerta}</p>}
        {status?.s === 'erro' && <p className="text-xs text-red-600">{status.msg}</p>}
      </div>
      <SeloStatus status={status} />
      {onRemover && !status && (
        <button onClick={onRemover} className="text-gray-400 hover:text-red-500 ml-1" title="Remover">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  )
}

function SeloStatus({ status }: { status?: StatusItem }) {
  if (!status) return null
  const mapa: Record<string, [string, string]> = {
    pendente: ['Na fila', 'bg-gray-100 text-gray-600'],
    enviando: ['Enviando', 'bg-blue-100 text-blue-700'],
    enviado: ['Enviado', 'bg-green-100 text-green-700'],
    ja_existia: ['Já estava lá', 'bg-green-50 text-green-700'],
    erro: ['Falhou', 'bg-red-100 text-red-700'],
  }
  const [texto, cls] = mapa[status.s]
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${cls}`}>{texto}</span>
}

function BotaoIcone({ titulo, onClick, disabled, children }: {
  titulo: string; onClick: () => void; disabled?: boolean; children: React.ReactNode
}) {
  return (
    <button
      title={titulo}
      onClick={onClick}
      disabled={disabled}
      className="p-1 text-gray-400 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
    >
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">{children}</svg>
    </button>
  )
}

function Aviso({ cor, children }: { cor: 'red' | 'amber'; children: React.ReactNode }) {
  const cls = cor === 'red' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-amber-50 border-amber-200 text-amber-800'
  return <div className={`border px-4 py-3 rounded-lg text-sm ${cls}`}>{children}</div>
}

function Spinner({ escuro }: { escuro?: boolean }) {
  return (
    <span
      className={`inline-block w-4 h-4 border-2 rounded-full animate-spin ${
        escuro ? 'border-gray-300 border-t-gray-700' : 'border-white border-t-transparent'
      }`}
    />
  )
}
