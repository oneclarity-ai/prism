import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

const components: Components = {
  h1: (p) => <h1 className="mt-2 mb-3 text-xl font-semibold tracking-tight" {...p} />,
  h2: (p) => <h2 className="mt-6 mb-2 text-lg font-semibold tracking-tight" {...p} />,
  h3: (p) => <h3 className="mt-4 mb-2 font-semibold" {...p} />,
  p: (p) => <p className="my-2 text-sm leading-relaxed" {...p} />,
  ul: (p) => <ul className="my-2 list-disc space-y-1 pl-5 text-sm" {...p} />,
  ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-5 text-sm" {...p} />,
  li: (p) => <li className="leading-relaxed" {...p} />,
  code: (p) => <code className="bg-muted rounded px-1 py-0.5 font-mono text-[0.8em]" {...p} />,
  pre: (p) => <pre className="bg-muted my-3 overflow-x-auto rounded-lg p-3 text-xs" {...p} />,
  a: (p) => <a className="text-primary underline underline-offset-2" target="_blank" rel="noreferrer" {...p} />,
  blockquote: (p) => <blockquote className="text-muted-foreground my-3 border-l-2 pl-3 italic" {...p} />,
  table: (p) => <table className="my-3 w-full border-collapse text-sm" {...p} />,
  th: (p) => <th className="border px-2 py-1 text-left font-medium" {...p} />,
  td: (p) => <td className="border px-2 py-1" {...p} />,
}

/** Render Markdown (front matter stripped) with app typography. */
export function Markdown({ source }: { source: string }) {
  const body = source.replace(/^---\n[\s\S]*?\n---\n?/, '')
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {body}
    </ReactMarkdown>
  )
}
