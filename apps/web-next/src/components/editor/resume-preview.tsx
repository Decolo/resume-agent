"use client"

import * as React from "react"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

/** Subset of JSON Resume schema relevant for preview */
export interface JsonResume {
  basics?: {
    name?: string
    label?: string
    email?: string
    phone?: string
    url?: string
    summary?: string
    location?: {
      city?: string
      region?: string
      countryCode?: string
    }
  }
  work?: Array<{
    name?: string
    position?: string
    startDate?: string
    endDate?: string
    summary?: string
    highlights?: string[]
  }>
  education?: Array<{
    institution?: string
    area?: string
    studyType?: string
    startDate?: string
    endDate?: string
  }>
  skills?: Array<{
    name?: string
    keywords?: string[]
  }>
  projects?: Array<{
    name?: string
    description?: string
    url?: string
    highlights?: string[]
  }>
}

interface ResumePreviewProps {
  resume: JsonResume
  className?: string
}

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h2>
      <Separator />
      {children}
    </section>
  )
}

function DateRange({ start, end }: { start?: string; end?: string }) {
  if (!start) return null
  return (
    <span className="text-xs text-muted-foreground">
      {start} &mdash; {end || "Present"}
    </span>
  )
}

export function ResumePreview({ resume, className }: ResumePreviewProps) {
  const { basics, work, education, skills, projects } = resume

  return (
    <ScrollArea className={cn("h-full", className)}>
      <div className="mx-auto max-w-2xl space-y-6 p-6 font-sans">
        {/* Header */}
        {basics && (
          <header className="space-y-1 text-center">
            {basics.name && (
              <h1 className="text-2xl font-bold tracking-tight">
                {basics.name}
              </h1>
            )}
            {basics.label && (
              <p className="text-sm text-muted-foreground">{basics.label}</p>
            )}
            <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
              {basics.email && <span>{basics.email}</span>}
              {basics.phone && <span>{basics.phone}</span>}
              {basics.location?.city && (
                <span>
                  {basics.location.city}
                  {basics.location.region && `, ${basics.location.region}`}
                </span>
              )}
            </div>
          </header>
        )}

        {/* Summary */}
        {basics?.summary && (
          <Section title="Summary">
            <p className="text-sm leading-relaxed">{basics.summary}</p>
          </Section>
        )}

        {/* Experience */}
        {work && work.length > 0 && (
          <Section title="Experience">
            <div className="space-y-4">
              {work.map((job, i) => (
                <div key={i} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold">{job.position}</h3>
                    <DateRange start={job.startDate} end={job.endDate} />
                  </div>
                  {job.name && (
                    <p className="text-xs text-muted-foreground">{job.name}</p>
                  )}
                  {job.summary && (
                    <p className="text-sm leading-relaxed">{job.summary}</p>
                  )}
                  {job.highlights && job.highlights.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-4 text-sm">
                      {job.highlights.map((h, j) => (
                        <li key={j}>{h}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Education */}
        {education && education.length > 0 && (
          <Section title="Education">
            <div className="space-y-3">
              {education.map((edu, i) => (
                <div key={i} className="flex items-baseline justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">
                      {edu.studyType && `${edu.studyType} in `}
                      {edu.area}
                    </p>
                    {edu.institution && (
                      <p className="text-xs text-muted-foreground">
                        {edu.institution}
                      </p>
                    )}
                  </div>
                  <DateRange start={edu.startDate} end={edu.endDate} />
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Skills */}
        {skills && skills.length > 0 && (
          <Section title="Skills">
            <div className="space-y-2">
              {skills.map((group, i) => (
                <div key={i}>
                  {group.name && (
                    <p className="mb-1 text-xs font-medium">{group.name}</p>
                  )}
                  <div className="flex flex-wrap gap-1">
                    {group.keywords?.map((kw, j) => (
                      <Badge key={j} variant="secondary">
                        {kw}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Projects */}
        {projects && projects.length > 0 && (
          <Section title="Projects">
            <div className="space-y-3">
              {projects.map((proj, i) => (
                <div key={i} className="space-y-1">
                  <h3 className="text-sm font-semibold">{proj.name}</h3>
                  {proj.description && (
                    <p className="text-sm leading-relaxed">{proj.description}</p>
                  )}
                  {proj.highlights && proj.highlights.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-4 text-sm">
                      {proj.highlights.map((h, j) => (
                        <li key={j}>{h}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </ScrollArea>
  )
}
