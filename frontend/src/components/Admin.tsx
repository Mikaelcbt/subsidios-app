import { useEffect, useState } from 'react'
import type { DriveStatus } from './EnvioDrive'

interface Usuario {
  id: string
  email: string
  nome: string | null
  criado_em: string | null
  ultimo_login: string | null
  confirmado: boolean
  admin: boolean
}

interface EnvioLog {
  envio_id: string
  user_email: string | null
  autor: string
  processo: string
  caminho: string | null
  url: string | null
  total_itens: number
  enviados: number
  ja_existiam: number
  falhas: number
  criado_em: string
  atualizado_em: string
}

function dataHora(iso: string | null) {
  if (!iso) return 'nunca'
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

async function buscar<T>(url: string, token: string): Promise<T> {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) {
    let msg = 'Erro ao carregar'
    try { msg = (await res.json()).detail || msg } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export function Admin({ token }: { token: string }) {
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null)
  const [envios, setEnvios] = useState<EnvioLog[] | null>(null)
  const [drive, setDrive] = useState<DriveStatus | null>(null)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [filtro, setFiltro] = useState('')

  const carregar = () => {
    setErros({})
    buscar<{ usuarios: Usuario[] }>('/api/admin/usuarios', token)
      .then(d => setUsuarios(d.usuarios))
      .catch(e => setErros(p => ({ ...p, usuarios: e.message })))
    buscar<{ envios: EnvioLog[] }>('/api/admin/envios', token)
      .then(d => setEnvios(d.envios))
      .catch(e => setErros(p => ({ ...p, envios: e.message })))
    buscar<DriveStatus>('/api/admin/drive', token)
      .then(setDrive)
      .catch(e => setErros(p => ({ ...p, drive: e.message })))
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(carregar, [token])

  const f = filtro.trim().toLowerCase()
  const enviosFiltrados = (envios ?? []).filter(e =>
    !f || [e.autor, e.processo, e.user_email ?? ''].some(v => v.toLowerCase().includes(f)),
  )
  const hoje = new Date().toDateString()
  const enviosHoje = (envios ?? []).filter(e => new Date(e.criado_em).toDateString() === hoje).length
  const comFalha = (envios ?? []).filter(e => e.falhas > 0).length

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Painel de ADM</h2>
          <p className="text-gray-500 mt-1">Usuários, histórico de envios e conexão com o Drive.</p>
        </div>
        <button onClick={carregar} className="text-sm bg-white border border-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-50">
          Atualizar
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card label="Usuários" valor={usuarios?.length} />
        <Card label="Envios (últimos 200)" valor={envios?.length} />
        <Card label="Envios hoje" valor={envios ? enviosHoje : undefined} />
        <Card label="Envios com falha" valor={envios ? comFalha : undefined} alerta={comFalha > 0} />
      </div>

      <Bloco titulo="Drive" erro={erros.drive}>
        {drive && (
          <div className="px-6 py-4 text-sm space-y-2">
            {!drive.configurado ? (
              <p className="text-amber-700">Não configurado. Falta a credencial do Google no Railway.</p>
            ) : (
              <>
                <p className="text-gray-700">
                  <span className="text-gray-500">Modo:</span>{' '}
                  {drive.teste ? 'teste (pasta no Meu Drive)' : drive.modo === 'conta_servico' ? 'conta de serviço' : 'conta do escritório'}
                  {drive.conta && <> · <span className="font-mono">{drive.conta}</span></>}
                </p>
                {drive.erro && <p className="text-red-700">{drive.erro}</p>}
                <div className="flex flex-wrap gap-2">
                  {drive.faixas.map(fx => (
                    <span key={fx.nome} className="text-xs bg-green-50 text-green-700 px-2 py-1 rounded-full">
                      {fx.de} a {fx.ate} · {fx.nome}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </Bloco>

      <Bloco
        titulo="Histórico de envios"
        erro={erros.envios}
        extra={
          <input
            value={filtro}
            onChange={e => setFiltro(e.target.value)}
            placeholder="Buscar autor, processo ou operador"
            className="text-sm px-3 py-1.5 border border-gray-300 rounded-lg w-64 max-w-full"
          />
        }
      >
        {envios && (
          enviosFiltrados.length === 0 ? (
            <p className="px-6 py-4 text-sm text-gray-500">Nenhum envio ainda.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left">
                    <th className="px-4 py-2 font-medium text-gray-500">Quando</th>
                    <th className="px-4 py-2 font-medium text-gray-500">Autor / processo</th>
                    <th className="px-4 py-2 font-medium text-gray-500">Operador</th>
                    <th className="px-4 py-2 font-medium text-gray-500">Arquivos</th>
                    <th className="px-4 py-2 font-medium text-gray-500"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {enviosFiltrados.map(e => (
                    <tr key={e.envio_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2 text-gray-600 whitespace-nowrap">{dataHora(e.criado_em)}</td>
                      <td className="px-4 py-2">
                        <p className="text-gray-900">{e.autor}</p>
                        <p className="text-xs text-gray-500 font-mono">{e.processo}</p>
                      </td>
                      <td className="px-4 py-2 text-gray-600">{e.user_email}</td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        <span className="text-gray-700">{e.enviados + e.ja_existiam}/{e.total_itens}</span>
                        {e.ja_existiam > 0 && <span className="text-xs text-gray-500"> ({e.ja_existiam} já estavam)</span>}
                        {e.falhas > 0 && <span className="ml-2 text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{e.falhas} falha(s)</span>}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {e.url && (
                          <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline whitespace-nowrap">
                            Abrir pasta
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Bloco>

      <Bloco titulo="Usuários" erro={erros.usuarios}>
        {usuarios && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="px-4 py-2 font-medium text-gray-500">Nome</th>
                  <th className="px-4 py-2 font-medium text-gray-500">E-mail</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Cadastro</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Último login</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {usuarios.map(u => (
                  <tr key={u.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-900">
                      {u.nome || '—'}
                      {u.admin && <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">ADM</span>}
                    </td>
                    <td className="px-4 py-2 text-gray-600">
                      {u.email}
                      {!u.confirmado && <span className="ml-2 text-xs text-amber-700">e-mail não confirmado</span>}
                    </td>
                    <td className="px-4 py-2 text-gray-600 whitespace-nowrap">{dataHora(u.criado_em)}</td>
                    <td className="px-4 py-2 text-gray-600 whitespace-nowrap">{dataHora(u.ultimo_login)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Bloco>
    </div>
  )
}

function Card({ label, valor, alerta }: { label: string; valor?: number; alerta?: boolean }) {
  return (
    <div className={`rounded-xl p-4 ${alerta ? 'bg-red-50 text-red-700' : 'bg-white border border-gray-200 text-gray-900'}`}>
      <p className="text-2xl font-bold">{valor ?? '…'}</p>
      <p className="text-sm opacity-70">{label}</p>
    </div>
  )
}

function Bloco({ titulo, erro, extra, children }: {
  titulo: string; erro?: string; extra?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold text-gray-900">{titulo}</h3>
        {extra}
      </div>
      {erro ? <p className="px-6 py-4 text-sm text-red-700">{erro}</p> : children}
    </div>
  )
}
