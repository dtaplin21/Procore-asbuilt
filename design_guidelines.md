# Design Guidelines: QC/QA AI Automation Platform

## Design Approach

**Selected System**: Material Design 3 + Linear-inspired B2B SaaS patterns  
**Rationale**: Enterprise construction management platform requiring information-dense layouts, clear data hierarchy, and mobile-first field operations. Material Design provides robust component library for complex data visualization while Linear's aesthetic ensures modern B2B credibility.

**Core Principles**:
1. **Data clarity over decoration** - Construction professionals need instant comprehension
2. **AI insights prominence** - Visually distinguish automated findings from manual data
3. **Status-driven design** - Color-coded object states (approved/pending/rejected) as primary visual language
4. **Mobile-field-first** - Touch-optimized for outdoor tablet/phone use

---

## Typography

**Primary Font**: Inter (Google Fonts)  
**Secondary Font**: JetBrains Mono (for technical data, object IDs, CAD references)

**Hierarchy**:
- **H1**: Inter 32px/700 - Page titles ("Shop Drawing Review")
- **H2**: Inter 24px/600 - Section headers ("Pending Submittals")
- **H3**: Inter 18px/600 - Card titles ("Manhole MH-047")
- **Body Large**: Inter 16px/400 - Primary content
- **Body**: Inter 14px/400 - Secondary content, table data
- **Caption**: Inter 12px/500 - Labels, metadata, timestamps
- **Code/Technical**: JetBrains Mono 14px/400 - Object IDs, drawing references

---

## Layout System

**Spacing Scale**: Tailwind units **2, 4, 6, 8, 12, 16** (p-2, m-4, gap-8, etc.)

**Container Strategy**:
- Dashboard content: `max-w-7xl mx-auto px-6`
- Data tables: Full width with horizontal scroll
- Modal dialogs: `max-w-4xl` for detail views
- Mobile: `px-4` with full-width components

**Grid Patterns**:
- **Dashboard cards**: `grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6`
- **Object lists**: Single column with dividers for scan-ability
- **Drawing viewer**: Full-width canvas with overlay panels

---

## Component Library

### Navigation
- **Top bar**: Fixed header with Procore sync status indicator, project switcher, user menu
- **Sidebar**: Collapsible (mobile) with icon-based primary nav (Submittals, RFIs, Inspections, As-Builts, Settings)
- **Breadcrumbs**: Below header for deep navigation paths

### Data Display
- **Status cards**: Material-style elevated cards with AI confidence scores (0-100%) as progress rings
- **Object tables**: Sticky headers, row selection, inline status badges, sortable columns
- **Drawing viewer**: Full-screen canvas with floating toolbar, pinch-to-zoom, object highlighting on hover
- **Timeline**: Vertical timeline for submittal → approval → installation → as-built lineage

### Forms & Inputs
- **Material Design 3** filled text fields with floating labels
- **File uploads**: Drag-drop zones with AI processing indicators ("Analyzing shop drawing...")
- **Status selectors**: Radio button groups with visual icons (checkmark/clock/x)
- **Smart suggestions**: AI-powered autocomplete dropdowns for object linking

### AI-Specific Components
- **AI insight panels**: Distinct card style with subtle glow/border to differentiate AI findings from manual data
- **Compliance checklist**: Auto-generated from spec analysis with pass/fail indicators
- **Photo comparison**: Side-by-side (shop drawing vs. field photo) with AI-detected deviation annotations
- **Object recognition overlay**: Transparent colored shapes on drawings with click-to-inspect

### Mobile-Specific
- **Bottom nav bar**: Large touch targets for primary actions (Capture Photo, Create RFI, Start Inspection)
- **Swipe actions**: Left-swipe for quick status changes
- **Camera integration**: Full-screen capture with AI object detection in real-time

---

## Interaction Patterns

**Hover states**: Subtle elevation increase, no background transitions  
**Loading states**: Skeleton screens for data tables, spinner with "AI analyzing..." for processing  
**Notifications**: Toast messages (top-right) for sync confirmations, inline alerts for AI findings  
**Modals**: Blur backdrop, slide-in animation from right for detail views  
**Animations**: Minimal - only for state changes (status badge pulse, AI processing indicator)

---

## Visual Language

**Status Color System** (Material Design semantics):
- Approved: Green badges/borders
- Pending Review: Amber badges
- Rejected/Issues: Red badges
- AI Processing: Blue pulse animation
- Not Started: Gray

**Visual Hierarchy**:
1. Critical AI alerts (non-compliance) - Red bordered panels
2. Status indicators - Bold badges
3. Object metadata - Subdued gray text
4. Secondary actions - Ghost buttons

**Iconography**: Material Symbols (via Google Fonts) - use Outlined variant for consistency

---

## Images

**Hero Image**: NOT applicable - this is a dashboard application, not a marketing site. No hero sections.

**Drawing/Photo Assets**:
- **Construction drawings**: Display full-bleed in viewer with pan/zoom controls
- **Field photos**: Thumbnail grids (3-4 per row) with lightbox expansion
- **Shop drawing PDFs**: Embedded viewer with annotation tools
- **Object thumbnails**: 48x48px circles with AI-extracted object previews

**Placeholder strategy**: Use construction-related icon placeholders (hard hat, blueprint, etc.) for empty states

---

## Accessibility

- WCAG AA contrast ratios for all text
- Keyboard navigation for all interactive elements
- Screen reader labels for AI-generated insights
- Focus indicators (2px blue outline) on all focusable elements
- Touch targets minimum 48x48px for mobile field use
- High-contrast mode support for outdoor visibility