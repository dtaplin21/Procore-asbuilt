# QC/QA AI Automation Platform

## Overview

This is an AI-powered Quality Control and Quality Assurance platform for the construction industry. The application automates submittal reviews, inspections, RFI management, and as-built generation with Procore integration capabilities. It provides construction professionals with intelligent drawing analysis, object recognition, and predictive as-built generation to streamline quality control workflows.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: React 18 with TypeScript
- **Routing**: Wouter (lightweight client-side routing)
- **State Management**: TanStack React Query for server state caching and synchronization
- **UI Components**: Shadcn/ui component library built on Radix UI primitives
- **Styling**: Tailwind CSS with CSS variables for theming (light/dark mode support)
- **Build Tool**: Vite with HMR support

The frontend follows a page-based structure with reusable components. Key pages include Dashboard, Submittals, RFIs, Inspections, Objects, and Settings. Custom components handle AI-specific visualizations like score rings and insight cards.

### Backend Architecture
- **Framework**: Express.js with TypeScript
- **API Design**: RESTful JSON API endpoints under `/api/*`
- **Database ORM**: Drizzle ORM with PostgreSQL dialect
- **Schema Validation**: Zod with drizzle-zod integration for type-safe schemas

The backend uses a simple storage abstraction layer (`server/storage.ts`) that defines interfaces for data operations. This allows flexibility in switching between in-memory storage and database-backed storage.

### Data Models
Core entities include:
- **Users**: Authentication and user management
- **Projects**: Construction projects with Procore sync status
- **Submittals**: Shop drawing submissions with AI compliance scores
- **RFIs**: Request for Information tracking
- **Inspections**: Field inspection management
- **DrawingObjects**: CAD objects tracked through lifecycle stages
- **AIInsights**: AI-generated recommendations and compliance findings

### Build and Development
- **Development**: `npm run dev` runs Vite dev server with Express backend
- **Production Build**: Custom build script bundles server with esbuild, client with Vite
- **Database Migrations**: Drizzle Kit for schema management (`npm run db:push`)

### Design System
Material Design 3 inspired with Linear-style B2B SaaS patterns. Mobile-first approach for field operations with status-driven color coding (approved/pending/rejected). Typography uses Inter for UI and JetBrains Mono for technical data.

## External Dependencies

### Database
- **PostgreSQL**: Primary database (configured via `DATABASE_URL` environment variable)
- **Drizzle ORM**: Database toolkit with migrations support

### Third-Party Integrations
- **Procore**: Construction management platform integration (planned/mockable)
- **AI Services**: Architecture supports integration with AI providers for drawing analysis and compliance checking

### Key NPM Packages
- **@tanstack/react-query**: Server state management
- **Radix UI**: Accessible component primitives (dialog, dropdown, tabs, etc.)
- **class-variance-authority**: Component variant management
- **date-fns**: Date formatting utilities
- **react-day-picker**: Calendar component
- **embla-carousel-react**: Carousel functionality
- **recharts**: Data visualization charts
- **vaul**: Drawer component
- **wouter**: Lightweight routing