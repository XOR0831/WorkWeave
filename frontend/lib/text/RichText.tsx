import { Fragment, type ReactNode } from "react";

/**
 * Tutor replies and source excerpts use light Markdown (# headings, **bold**, *italic*, numbered and
 * bulleted lists, and simple | pipe | tables).
 * This renders just that subset as React elements; it never interprets HTML, links or images, so
 * model output can't inject markup. Anything else stays as plain text.
 */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\*(\S(?:.*?\S)?)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[1] !== undefined ? <strong key={`${key}-${i++}`}>{m[1]}</strong> : <em key={`${key}-${i++}`}>{m[2]}</em>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const ORDERED = /^\s*(\d+)[.)]\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;
const TABLE_ROW = /^\s*\|(.*)\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

export function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let para: string[] = [];
  let list: { ordered: boolean; start: number; items: string[] } | null = null;
  let table: string[][] | null = null;
  const flushTable = () => {
    if (table) {
      const k = `t${blocks.length}`;
      const [head, ...rows] = table;
      blocks.push(
        <div key={k} className="table-wrap">
          <table className="rich-table">
            <thead>
              <tr>
                {head!.map((c, i) => (
                  <th key={i} scope="col">
                    {inline(c, `${k}-h${i}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, i) => (
                    <td key={i}>{inline(c, `${k}-${ri}-${i}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      table = null;
    }
  };
  const flushPara = () => {
    if (para.length) {
      const k = `p${blocks.length}`;
      blocks.push(
        <p key={k}>
          {para.map((l, i) => (
            <Fragment key={i}>
              {i > 0 && <br />}
              {inline(l, `${k}-${i}`)}
            </Fragment>
          ))}
        </p>,
      );
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      const k = `l${blocks.length}`;
      const items = list.items.map((it, i) => <li key={i}>{inline(it, `${k}-${i}`)}</li>);
      blocks.push(list.ordered ? <ol key={k} start={list.start}>{items}</ol> : <ul key={k}>{items}</ul>);
      list = null;
    }
  };
  for (const line of lines) {
    const row = TABLE_ROW.exec(line);
    if (row) {
      if (TABLE_RULE.test(line)) continue; // the |---|---| line under the header
      flushPara();
      flushList();
      (table ??= []).push(row[1]!.split("|").map((c) => c.trim()));
      continue;
    }
    flushTable();
    const h = HEADING.exec(line);
    if (h) {
      flushPara();
      flushList();
      const k = `h${blocks.length}`;
      blocks.push(
        <p key={k} className="rich-h">
          <strong>{inline(h[1]!, k)}</strong>
        </p>,
      );
      continue;
    }
    const o = ORDERED.exec(line);
    const b = o ? null : BULLET.exec(line);
    if (o || b) {
      flushPara();
      const ordered = Boolean(o);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, start: o ? Number(o[1]) : 1, items: [] };
      }
      list.items.push(o ? o[2]! : b![1]!);
    } else if (!line.trim()) {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line.trim());
    }
  }
  flushPara();
  flushList();
  flushTable();
  return <div className="rich">{blocks}</div>;
}
