import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowRight, Bot, Eye, EyeOff, Lock, Mail, ShieldCheck, Sparkles, Wallet } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { z } from 'zod'

import { useLogin, useMe } from '@/api/hooks'
import { Logo, LogoMark } from '@/components/common/logo'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'

const schema = z.object({
  email: z.string().min(3, 'Enter your email').regex(/^[^@\s]+@[^@\s]+$/, 'Enter a valid email'),
  password: z.string().min(1, 'Enter your password'),
})
type Values = z.infer<typeof schema>

const HIGHLIGHTS = [
  { icon: Bot, title: 'Agents as teammates', text: 'Onboard QA, Sales and Marketing agents with roles, tools and budgets.' },
  { icon: ShieldCheck, title: 'Human in the loop', text: 'Risky actions wait for your approval before they happen.' },
  { icon: Wallet, title: 'Cost under control', text: 'Per-run and monthly budgets with a full audit trail.' },
]

export function LoginPage() {
  const me = useMe()
  const login = useLogin()
  const navigate = useNavigate()
  const location = useLocation()
  const [show, setShow] = useState(false)
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  if (me.data) return <Navigate to="/" replace />

  const onSubmit = form.handleSubmit((values) =>
    login.mutate(values, {
      onSuccess: () => navigate((location.state as { from?: string } | null)?.from ?? '/', { replace: true }),
    }),
  )

  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-zinc-950 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="bg-grid absolute inset-0 opacity-[0.15]" />
        <div className="absolute -top-40 -left-40 size-[32rem] rounded-full bg-indigo-600/40 blur-3xl" />
        <div className="absolute -right-32 -bottom-40 size-[28rem] rounded-full bg-fuchsia-600/30 blur-3xl" />

        <div className="relative flex items-center gap-2.5">
          <LogoMark className="size-9" />
          <span className="text-lg font-semibold tracking-tight">OneClarity</span>
        </div>

        <div className="relative space-y-8">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/80">
              <Sparkles className="size-3.5 text-amber-300" /> Agent Platform · QA Agent preview
            </div>
            <h1 className="text-4xl leading-tight font-semibold tracking-tight">
              Your army of AI agents,
              <br />
              <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-fuchsia-300 bg-clip-text text-transparent">
                managed like a team.
              </span>
            </h1>
          </div>
          <ul className="space-y-5">
            {HIGHLIGHTS.map((h) => (
              <li key={h.title} className="flex gap-4">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                  <h.icon className="size-5 text-indigo-300" />
                </div>
                <div>
                  <div className="font-medium">{h.title}</div>
                  <div className="text-sm text-white/60">{h.text}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative text-xs text-white/40">© {new Date().getFullYear()} OneClarity AI</div>
      </div>

      {/* Form panel */}
      <div className="relative flex flex-col p-6 md:p-10">
        <div className="flex items-center justify-between">
          <Logo className="lg:invisible" />
          <ThemeToggle />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <form onSubmit={onSubmit} className="w-full max-w-sm space-y-8" noValidate>
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold tracking-tight">Welcome back</h2>
              <p className="text-muted-foreground text-sm">Sign in to manage your agents and tasks.</p>
            </div>

            {login.isError && (
              <Alert variant="destructive">
                <AlertDescription>{login.error.message}</AlertDescription>
              </Alert>
            )}

            <FieldGroup>
              <Field data-invalid={!!form.formState.errors.email}>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <InputGroup>
                  <InputGroupInput
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@oneclarity.ai"
                    autoFocus
                    {...form.register('email')}
                  />
                  <InputGroupAddon>
                    <Mail />
                  </InputGroupAddon>
                </InputGroup>
                <FieldError errors={[form.formState.errors.email]} />
              </Field>

              <Field data-invalid={!!form.formState.errors.password}>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <InputGroup>
                  <InputGroupInput
                    id="password"
                    type={show ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    {...form.register('password')}
                  />
                  <InputGroupAddon>
                    <Lock />
                  </InputGroupAddon>
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      size="icon-xs"
                      onClick={() => setShow((s) => !s)}
                      aria-label={show ? 'Hide password' : 'Show password'}
                    >
                      {show ? <EyeOff /> : <Eye />}
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
                <FieldError errors={[form.formState.errors.password]} />
              </Field>
            </FieldGroup>

            <Button type="submit" size="lg" className="w-full" disabled={login.isPending}>
              {login.isPending ? <Spinner /> : null}
              Sign in
              {!login.isPending && <ArrowRight />}
            </Button>

            <p className="text-muted-foreground text-center text-xs">
              First time? Run <code className="bg-muted rounded px-1 py-0.5 font-mono">python -m app.db.seed</code> and use
              the admin from <code className="bg-muted rounded px-1 py-0.5 font-mono">backend/.env</code>.
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}
