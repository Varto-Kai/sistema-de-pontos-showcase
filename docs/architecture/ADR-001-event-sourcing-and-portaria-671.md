# ADR-001: Adoção de Event Sourcing & Ledger Imutável no Registro de Ponto

- **Status:** Aprovado & Implementado
- **Decisores:** Victor Lacerda (Lead Developer & Author)
- **Data:** Outubro/2026
- **Contexto Técnico:** REP-P (Registrador Eletrônico de Ponto por Programa) e Portaria MTP nº 671/2021

---

## 1. Contexto & Problema

O registro de ponto eletrônico no Brasil é regulamentado pela **Portaria MTP nº 671/2021**, que estabelece requisitos de alta segurança jurídica para softwares classificados como **REP-P**:
1. **Art. 74 e 80 (Coleta Livre e Irrestrita):** O colaborador não pode ter seu ponto recusado ou bloqueado sob nenhuma hipótese.
2. **Inviolabilidade do Dado:** É expressamente proibido alterar (`UPDATE`), apagar (`DELETE`) ou sobrescrever qualquer marcação de ponto pretérita.
3. **Não-Repúdio e Rastreabilidade:** Cada registro deve possuir um Número Sequencial de Registro (NSR) contínuo e sem saltos, além de assinatura digital e hash criptográfico SHA-256 encadeado com o registro anterior.

No modelo relacional tradicional (CRUD convencional com tabelas `pontos` mutáveis), a integridade ficava vulnerável a operações acidentais de banco ou atualizações diretas de registros, o que invalida juridicamente o espelho de ponto em auditorias fiscais do Ministério do Trabalho.

---

## 2. Decisão

Decidimos que o core transacional de coleta e tratamento de ponto **NÃO** utilizaria persistência baseada em CRUD mutável.

Adotamos a arquitetura de **Event Sourcing** com **Cadeia Criptográfica (Ledger)**:
1. Toda marcação de ponto emite um evento imutável (`PontoRegistrado`);
2. Os eventos são persistidos em uma stream append-only (`event_store`);
3. Cada batida calcula o hash `SHA-256(NSR + CPF + DataHora + HashAnterior)`;
4. O NSR é gerado monotonicamente garantindo ausência de lacunas fiscais;
5. Correções de ponto pelo RH (PTRP) não alteram a batida original; elas emitem novos eventos de tratamento (`PontoAjustado`, `AbonoAtestadoRegistrado`), preservando o histórico original intacto para o auditor fiscal.

---

## 3. Consequências

### Pontos Positivos:
- **Blindagem Jurídica Absoluta:** O sistema atende nativamente às exigências da fiscalização e da emissão dos arquivos oficiais AFD (Arquivo Fonte de Dados) e AEJ (Arquivo Eletrônico de Jornada).
- **Auditabilidade Forense:** Qualquer tentativa de adulteração de registro quebra a cadeia de hashes SHA-256, sendo detectada instantaneamente pela rotina de auditoria.
- **Time-Travel & Replay:** Permite recalcular retroativamente fechamentos de competência com 100% de reprodutibilidade matemática.

### Compensações / Desafios Superados:
- Maior complexidade na modelagem de leitura (CQRS), resolvida através de projeções de leitura limpas atualizadas deterministicamente.
