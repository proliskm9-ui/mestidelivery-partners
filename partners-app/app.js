/**
 * MestiDelivery Partners Mini App — Cyber-Luxe Edition v6.0
 * Fully Styled, Pixel-Perfect Architecture for Kitchen & Courier
 */

(function () {
  'use strict';

  // 1. Embedded Style Injection Guarantee
  const EMBEDDED_CSS = `/* ==========================================================================
   MestiDelivery Partners — Minimalist Luxury Edition (v7.0)
   Designed to match MestiDelivery Client App & Official Brand Guidelines.
   Zero AI clichés, pure obsidian surfaces, surgical #21EA7C accents,
   and executive-grade typography (Montserrat + Archivo).
   ========================================================================== */

:root {
  /* Matte Obsidian Palette */
  --bg: #0A0B0E;
  --bg-subtle: #0E1015;
  
  --surface: #12141B;
  --surface-hover: #161922;
  --surface-raised: #181B26;
  --surface-subtle: #14161F;
  --surface-pill: #151720;
  --surface-glass: rgba(18, 20, 27, 0.88);
  
  /* Hairline Precision Borders */
  --border: rgba(255, 255, 255, 0.05);
  --border-subtle: rgba(255, 255, 255, 0.035);
  --border-highlight: rgba(255, 255, 255, 0.09);
  --border-strong: rgba(255, 255, 255, 0.16);
  
  /* Typography Colors */
  --text-primary: #F8FAFC;
  --text-secondary: #94A3B8;
  --text-muted: #5B6271;
  --text-dim: #3F4452;
  
  /* Official Mesti Brand Colors */
  --brand: #21EA7C;
  --brand-pressed: #00C853;
  --brand-dim: rgba(33, 234, 124, 0.10);
  --brand-border: rgba(33, 234, 124, 0.28);
  --brand-contrast: #041208;

  --emerald: #21EA7C;
  --emerald-dim: rgba(33, 234, 124, 0.10);
  
  --amber: #F59E0B;
  --amber-dim: rgba(245, 158, 11, 0.12);
  
  --crimson: #EF4444;
  --crimson-dim: rgba(239, 68, 68, 0.12);
  
  --sky: #38BDF8;
  --sky-dim: rgba(56, 189, 248, 0.12);
  
  --violet: #A855F7;
  --violet-dim: rgba(168, 85, 247, 0.12);

  /* Typography */
  --font: "Montserrat", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-display: "Archivo", "Montserrat", sans-serif;

  /* Insets */
  --tg-safe-top: 16px;
  --tg-safe-bottom: 24px;
  --nav-height: 58px;
}

/* ==========================================================================
   Reset & Native Scroll Physics
   ========================================================================== */

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  -webkit-tap-highlight-color: transparent;
}

html {
  min-height: 100%;
  height: 100%;
  background-color: var(--bg);
  overflow-y: scroll;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
}

body {
  min-height: 100%;
  background-color: var(--bg);
  color: var(--text-primary);
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  padding-bottom: calc(var(--tg-safe-bottom, 24px) + 84px);
  user-select: none;
  -webkit-user-select: none;
}

input, button, textarea, select {
  font-family: inherit;
  font-size: inherit;
  border: none;
  outline: none;
}

/* ==========================================================================
   Splash / Loader
   ========================================================================== */

.app-splash {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  gap: 16px;
  background: var(--bg);
}

.splash-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255, 255, 255, 0.08);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.splash-text {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
  letter-spacing: 0.04em;
}

/* ==========================================================================
   App Layout & Top Header (Official Mesti Partners Brandmark)
   ========================================================================== */

.app-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg);
}

.top-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(var(--tg-safe-top, 12px) + 6px) 16px 12px 16px;
  background: rgba(10, 11, 14, 0.90);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid var(--border);
}

.brand-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.brand-logo-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-logo-img {
  width: 22px;
  height: 22px;
  object-fit: contain;
  flex-shrink: 0;
}

.brand-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 3px;
  line-height: 1;
}

.brand-title-mesti {
  font-family: var(--font-display);
  font-weight: 900;
  font-size: 14.5px;
  letter-spacing: -0.01em;
  color: var(--brand);
}

.brand-title-deliv {
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 14.5px;
  letter-spacing: -0.01em;
  color: #FFFFFF;
}

.brand-title-sub {
  font-family: var(--font);
  font-weight: 600;
  font-size: 9px;
  letter-spacing: 0.12em;
  color: #6B7280;
  margin-left: 3px;
  text-transform: uppercase;
}

.brand-entity-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 30px;
  font-size: 11.5px;
  font-weight: 600;
  color: #94A3B8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-entity-row .entity-dash {
  color: var(--brand);
  font-weight: 800;
}

.entity-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.icon-btn-quiet {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #13151D;
  border: 1px solid var(--border);
  color: #94A3B8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.18s ease;
}

.icon-btn-quiet:active {
  transform: scale(0.94);
}

.icon-btn-quiet.is-active {
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.25);
  background: rgba(33, 234, 124, 0.08);
}

.status-capsule-btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 100px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #13151D;
  border: 1px solid var(--border);
  font-family: var(--font);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #94A3B8;
  cursor: pointer;
  transition: all 0.18s ease;
}

.status-capsule-btn:active {
  transform: scale(0.96);
}

.status-capsule-btn.is-online {
  background: rgba(33, 234, 124, 0.08);
  border-color: rgba(33, 234, 124, 0.28);
  color: var(--brand);
}

.status-beacon-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748B;
  flex-shrink: 0;
}

.status-capsule-btn.is-online .status-beacon-dot {
  background: var(--brand);
  box-shadow: 0 0 5px rgba(33, 234, 124, 0.7);
}

/* ==========================================================================
   Executive Metric Strip (Replacing Clunky AI Boxes)
   ========================================================================== */

.metrics-strip {
  display: flex;
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  margin: 12px 16px 4px 16px;
  padding: 9px 4px;
}

.metric-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--border);
  padding: 0 6px;
}

.metric-col:last-child {
  border-right: none;
}

.metric-col-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 2px;
}

.metric-col-val {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 800;
  color: #F8FAFC;
  line-height: 1.2;
}

.metric-col-val.highlight {
  color: var(--brand);
}

/* Backward compatibility for legacy row */
.metrics-row {
  display: flex;
  gap: 8px;
  padding: 10px 16px 4px 16px;
}
.metric-tile {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.metric-tile .metric-label {
  font-size: 9.5px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}
.metric-tile .metric-value {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 800;
  color: #FFF;
}
.metric-tile .metric-value.highlight {
  color: var(--brand);
}

/* ==========================================================================
   Search Bar & Clean Capsule Filter Chips
   ========================================================================== */

.search-wrap {
  padding: 8px 16px 4px 16px;
}

.search-box {
  display: flex;
  align-items: center;
  height: 44px;
  background: #13151D;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 0 14px;
  gap: 10px;
  transition: border-color 0.18s ease;
}

.search-box:focus-within {
  border-color: rgba(33, 234, 124, 0.35);
}

.search-box svg {
  color: var(--brand);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #F8FAFC;
  font-family: var(--font);
  font-size: 13px;
  font-weight: 500;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-clear {
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 4px;
}

/* Single clean scrollable pill filter row */
.chips-scroll-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px 10px 16px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.chips-scroll-row::-webkit-scrollbar {
  display: none;
}

.filter-pill-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 13px;
  border-radius: 100px;
  background: #13151D;
  border: 1px solid var(--border-subtle);
  color: #8F95A0;
  font-family: var(--font);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-pill-btn:active {
  transform: scale(0.96);
}

.filter-pill-btn.is-active {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.30);
  font-weight: 700;
}

.pill-counter {
  font-size: 10px;
  font-weight: 800;
  background: rgba(255, 255, 255, 0.08);
  color: #FFF;
  border-radius: 100px;
  padding: 1px 6px;
  min-width: 16px;
  text-align: center;
}

.filter-pill-btn.is-active .pill-counter {
  background: var(--brand);
  color: #041208;
}

/* Segment nav compatibility */
.segments-nav {
  display: flex;
  gap: 6px;
  padding: 6px 16px;
  background: transparent;
}
.segment-item {
  flex: 1;
  height: 34px;
  border-radius: 100px;
  background: #13151D;
  border: 1px solid var(--border-subtle);
  color: #8F95A0;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.segment-item.is-active {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.30);
  font-weight: 700;
}
.badge-count {
  font-size: 10px;
  font-weight: 800;
  background: rgba(255, 255, 255, 0.08);
  color: #FFF;
  border-radius: 100px;
  padding: 1px 6px;
}
.segment-item.is-active .badge-count {
  background: var(--brand);
  color: #041208;
}

/* ==========================================================================
   Orders Feed & Luxury Foodtech Cards
   ========================================================================== */

.feed-container {
  display: flex;
  flex-direction: column;
  padding: 4px 0 16px 0;
}

/* Airy Minimal Empty State */
.empty-wrap {
  padding: 50px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.empty-icon-wrap {
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: #13151D;
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  margin-bottom: 14px;
}

.empty-headline {
  font-size: 15px;
  font-weight: 700;
  color: #E2E8F0;
  margin-bottom: 4px;
}

.empty-detail {
  font-size: 12.5px;
  color: var(--text-muted);
  max-width: 270px;
  line-height: 1.4;
}

/* Card Container */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 18px;
  margin: 0 16px 12px 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  transition: transform 0.18s ease;
}

.card.is-new-order {
  border-color: rgba(33, 234, 124, 0.28);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.card-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.order-id {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: -0.01em;
}

.order-elapsed {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

/* Status Tags */
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 25px;
  padding: 0 10px;
  border-radius: 100px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.status-tag-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.status-tag.status-new,
.status-tag.status-pending {
  background: rgba(33, 234, 124, 0.10);
  color: var(--brand);
  border: 1px solid rgba(33, 234, 124, 0.25);
}

.status-tag.status-confirmed,
.status-tag.status-preparing,
.status-tag.status-delivering,
.status-tag.status-on_the_way {
  background: rgba(56, 189, 248, 0.10);
  color: #38BDF8;
  border: 1px solid rgba(56, 189, 248, 0.25);
}

.status-tag.status-ready {
  background: rgba(245, 158, 11, 0.10);
  color: #F59E0B;
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.status-tag.status-delivered {
  background: rgba(255, 255, 255, 0.06);
  color: #94A3B8;
}

.status-tag.status-cancelled {
  background: rgba(239, 68, 68, 0.10);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.25);
}

/* Items List (Airy, No heavy table lines) */
.items-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.item-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.item-qty,
.item-qty-badge {
  background: #171922;
  color: #FFFFFF;
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  border-radius: 6px;
  padding: 2px 6px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  flex-shrink: 0;
}

.item-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #E2E8F0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-cost {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
  flex-shrink: 0;
}

/* Note Callout */
.note-callout {
  background: #151822;
  border-left: 2px solid var(--brand);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #CBD5E1;
  margin-bottom: 12px;
  line-height: 1.4;
}

/* Kitchen Card Summary */
.card-summary {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 10px 0 12px 0;
  border-top: 1px solid var(--border);
}

.card-summary span:first-child {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  text-transform: uppercase;
}

.total-amount {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 800;
  color: #FFFFFF;
}

/* Courier Vertical Route Block (Official Banner 5a) */
.courier-route-block {
  background: #0E1016;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  position: relative;
}

.route-node {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  position: relative;
  z-index: 2;
}

.route-marker-circle {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--brand);
  background: transparent;
  margin-top: 2px;
  flex-shrink: 0;
}

.route-marker-pin {
  width: 14px;
  height: 14px;
  color: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
  flex-shrink: 0;
}

.route-dash-connector {
  width: 2px;
  height: 18px;
  border-left: 2px dashed rgba(33, 234, 124, 0.35);
  margin-left: 6px;
  margin-top: 2px;
  margin-bottom: 2px;
}

.route-node-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.route-node-tag {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--brand);
  text-transform: uppercase;
}

.route-node-val {
  font-size: 13px;
  font-weight: 600;
  color: #F8FAFC;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Route card compatibility */
.route-card {
  background: #0E1016;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.route-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.route-dot {
  color: var(--brand);
  margin-top: 2px;
}
.route-body {
  display: flex;
  flex-direction: column;
}
.route-type {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--brand);
  text-transform: uppercase;
}
.route-name {
  font-size: 13px;
  font-weight: 600;
  color: #F8FAFC;
}

/* Courier Payout Row */
.courier-payout-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 8px 0;
  margin-bottom: 12px;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.payout-tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  text-transform: uppercase;
}

.payout-val {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 800;
  color: var(--brand);
}

/* ==========================================================================
   Minimalist Discreet Courier Chip & Avatar System (Zero AI Slop / Clutter)
   ========================================================================== */

.courier-avatar-container {
  position: relative;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1E293B, #0F172A);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.courier-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.courier-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-weight: 700;
  color: #F1F5F9;
  text-transform: uppercase;
  user-select: none;
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.16), rgba(33, 234, 124, 0.12));
}

/* Discreet Courier Chip in Kitchen Card (Zero shouting copy) */
.courier-compact-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px 4px 6px;
  margin-top: 8px;
  margin-bottom: 2px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
}

.courier-chip-left {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.courier-chip-name {
  font-size: 12.5px;
  font-weight: 600;
  color: #F1F5F9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}

.courier-chip-call {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.courier-chip-call:active {
  transform: scale(0.96);
  background: rgba(255, 255, 255, 0.12);
  color: #FFF;
}

/* Searching State (Quiet & Non-intrusive) */
.courier-compact-chip.is-searching {
  justify-content: flex-start;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.04);
}

.courier-searching-text {
  font-size: 11px;
  color: var(--text-muted);
}

.searching-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--amber);
  animation: pulseBeacon 1.8s infinite ease-in-out;
  flex-shrink: 0;
}

/* Refined Details Modal Courier Strip */
.courier-details-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
}

.courier-details-strip.is-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
}

.courier-details-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.courier-details-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.courier-details-name {
  font-size: 13.5px;
  font-weight: 600;
  color: #F8FAFC;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.courier-details-phone {
  font-size: 11.5px;
  color: var(--text-muted);
}

.courier-details-call-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: 9999px;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--sky);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.courier-details-call-btn:active {
  transform: scale(0.96);
  background: rgba(56, 189, 248, 0.22);
}

/* Identity Row in Courier Profile */
.account-identity-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Legacy fallback classes for safety */
.courier-info-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  margin-bottom: 8px;
}

.courier-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.courier-avatar-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--sky);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.courier-name-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.courier-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.courier-name {
  font-size: 12.5px;
  font-weight: 600;
  color: #F8FAFC;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.courier-call-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  text-decoration: none;
}

/* Action CTA Buttons (Clean, Solid, No Neon Halos) */
.btn-primary-action {
  width: 100%;
  height: 48px;
  border-radius: 14px;
  background: var(--brand);
  color: #041208;
  border: none;
  font-family: var(--font);
  font-size: 14.5px;
  font-weight: 800;
  letter-spacing: 0.01em;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
  margin-top: 6px;
}

.btn-primary-action:active {
  transform: scale(0.98);
  background: var(--brand-pressed);
}

.btn-primary-action.state-cook {
  background: #38BDF8;
  color: #041424;
}

.btn-primary-action.state-ready {
  background: #F59E0B;
  color: #1A1002;
}

.btn-secondary-danger {
  width: 100%;
  height: 38px;
  border-radius: 12px;
  background: transparent;
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.25);
  font-family: var(--font);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 6px;
  transition: all 0.18s ease;
}

.btn-secondary-danger:active {
  background: rgba(239, 68, 68, 0.08);
}

.btn-open-details {
  width: 100%;
  height: 36px;
  border-radius: 12px;
  background: #14161F;
  color: #94A3B8;
  border: 1px solid var(--border);
  font-family: var(--font);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  margin-bottom: 6px;
  transition: all 0.18s ease;
}

.btn-open-details:active {
  background: #181B26;
  color: #FFF;
}

.state-badge-waiting {
  width: 100%;
  height: 42px;
  border-radius: 12px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.22);
  color: #F59E0B;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  margin-top: 6px;
}

/* Obsolete details block removed in v8.1 */

/* Timeline Stepper */
.stepper-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
  margin: 16px 0;
}

.stepper-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  position: relative;
  z-index: 2;
}

.stepper-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #14161F;
  border: 1px solid var(--border);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.stepper-circle.is-done {
  background: rgba(33, 234, 124, 0.12);
  border-color: rgba(33, 234, 124, 0.35);
  color: var(--brand);
}

.stepper-circle.is-current {
  background: var(--brand);
  border-color: var(--brand);
  color: #041208;
}

.stepper-label {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-muted);
}

.stepper-label.is-active {
  color: #FFFFFF;
}

/* ==========================================================================
   Floating Frosted Glass Pill Bottom Navigation (From mesti-mobile.png)
   ========================================================================== */

.bottom-nav {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 32px);
  max-width: 380px;
  height: 58px;
  border-radius: 100px;
  background: rgba(18, 20, 27, 0.88);
  backdrop-filter: blur(28px);
  -webkit-backdrop-filter: blur(28px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 6px;
  z-index: 1000;
}

.tab-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: transparent;
  border: none;
  color: #64748B;
  cursor: pointer;
  position: relative;
  padding: 6px 12px;
  transition: color 0.18s ease;
}

.tab-btn:active {
  transform: scale(0.94);
}

.tab-btn.is-active {
  color: var(--brand);
}

.tab-btn.is-active::after {
  content: '';
  position: absolute;
  bottom: 1px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--brand);
}

.tab-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.tab-bubble {
  position: absolute;
  top: 1px;
  right: 6px;
  background: var(--brand);
  color: #041208;
  font-size: 9.5px;
  font-weight: 800;
  border-radius: 100px;
  padding: 1px 5px;
  min-width: 15px;
  text-align: center;
}

/* ==========================================================================
   Grouped Apple / Linear Settings & Profile Hub
   ========================================================================== */

.settings-group {
  margin-bottom: 20px;
}

.settings-group-header {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 0 16px 8px 16px;
}

.settings-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  overflow: hidden;
  margin: 0 16px;
}

.settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.settings-row:last-child {
  border-bottom: none;
}

/* Legacy profile section card compatibility */
.profile-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.profile-row-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.profile-row-toggle:last-child {
  border-bottom: none;
}

.profile-toggle-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 78%;
}

.profile-toggle-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #F8FAFC;
}

.profile-toggle-sub {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.35;
}

/* Prep time chips */
.profile-prep-chips {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.prep-chip {
  height: 38px;
  border-radius: 100px;
  background: #141620;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-family: var(--font);
  font-size: 11.5px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.prep-chip:active {
  transform: scale(0.96);
}

.prep-chip.is-active {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.35);
  font-weight: 700;
}

/* Courier transport chips */
.transport-chips {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.transport-chip {
  height: 42px;
  border-radius: 14px;
  background: #141620;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-family: var(--font);
  font-size: 12.5px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.transport-chip:active {
  transform: scale(0.96);
}

.transport-chip.is-active {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.35);
  font-weight: 700;
}

/* Apple-style Smooth Switch */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #232733;
  transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 100px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: #FFFFFF;
  transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--brand);
}

input:checked + .slider:before {
  transform: translateX(20px);
  background-color: #041208;
}

.btn-test-sound {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  border-radius: 100px;
  background: #141620;
  border: 1px solid var(--border);
  color: var(--brand);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 6px;
  align-self: flex-start;
}

/* FAQ Accordion */
.faq-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.faq-item {
  background: #13151D;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.faq-question {
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #E2E8F0;
  cursor: pointer;
}

.faq-chevron {
  color: var(--text-muted);
  transition: transform 0.2s ease;
}

.faq-item.is-open .faq-chevron {
  transform: rotate(180deg);
}

.faq-answer {
  padding: 0 14px 12px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
  display: none;
}

.faq-item.is-open .faq-answer {
  display: block;
}

/* ==========================================================================
   Menu Management & Dish Cards (Luxury Clean)
   ========================================================================== */

.menu-search-wrap {
  padding: 8px 16px;
}

.cat-pills-row {
  display: flex;
  gap: 6px;
  padding: 4px 16px 10px 16px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.cat-pill {
  height: 30px;
  padding: 0 12px;
  border-radius: 100px;
  background: #13151D;
  border: 1px solid var(--border-subtle);
  color: #8F95A0;
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.cat-pill.is-active {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.3);
  font-weight: 700;
}

.dish-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  margin: 0 16px 10px 16px;
  display: flex;
  gap: 12px;
}

.dish-img {
  width: 72px;
  height: 72px;
  border-radius: 12px;
  object-fit: cover;
  background: #161822;
  flex-shrink: 0;
}

.dish-body {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
  min-width: 0;
}

.dish-name {
  font-size: 14px;
  font-weight: 700;
  color: #F8FAFC;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dish-price {
  font-family: var(--font-display);
  font-size: 14.5px;
  font-weight: 800;
  color: var(--brand);
}

.dish-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-edit-dish {
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  background: #151822;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.btn-add-dish-primary {
  margin: 8px 16px 14px 16px;
  height: 44px;
  border-radius: 14px;
  background: #161822;
  border: 1px dashed rgba(33, 234, 124, 0.35);
  color: var(--brand);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
}

/* ==========================================================================
   Statistics & Analytics Hub
   ========================================================================== */

.stats-container {
  padding: 6px 0 16px 0;
}

.period-picker {
  display: flex;
  gap: 6px;
  padding: 6px 16px 12px 16px;
}

.period-btn {
  flex: 1;
  height: 32px;
  border-radius: 100px;
  background: #13151D;
  border: 1px solid var(--border-subtle);
  color: #8F95A0;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.period-btn.is-selected {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.3);
  font-weight: 700;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 0 16px 12px 16px;
}

.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  display: flex;
  flex-direction: column;
}

.kpi-label {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.kpi-num {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 800;
  color: #FFFFFF;
}

.kpi-num.emerald {
  color: var(--brand);
}

.kpi-sub {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}

.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  margin: 0 16px 12px 16px;
}

.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.chart-title {
  font-size: 13.5px;
  font-weight: 700;
  color: #F8FAFC;
}

.chart-sum {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 800;
  color: var(--brand);
}

.chart-bars-wrap {
  display: flex;
  align-items: flex-end;
  height: 120px;
  gap: 8px;
  padding-top: 8px;
}

.chart-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  gap: 6px;
}

.chart-col-track {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: flex-end;
  background: #151822;
  border-radius: 6px;
  overflow: hidden;
}

.chart-col-fill {
  width: 100%;
  background: var(--brand);
  border-radius: 6px;
  transition: height 0.3s ease;
}

.chart-col-fill.is-peak {
  background: #38BDF8;
}

.chart-col-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
}

/* ==========================================================================
   Modals & Toast
   ========================================================================== */

.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 200;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.modal-content {
  background: #141620;
  border: 1px solid var(--border-highlight);
  border-radius: 24px 24px 0 0;
  width: 100%;
  max-width: 480px;
  padding: 20px;
  max-height: 85vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.modal-title {
  font-size: 16px;
  font-weight: 800;
  color: #FFF;
}

.modal-close-btn {
  background: #191C28;
  color: #94A3B8;
  border: 1px solid var(--border);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.form-group {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  height: 42px;
  background: #0E1016;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0 12px;
  color: #FFF;
  font-family: var(--font);
  font-size: 13px;
}

.form-input:focus {
  border-color: var(--brand);
}

.modal-actions-row {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

/* Toast */
.toast-msg {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(18, 21, 30, 0.95);
  border: 1px solid var(--border-highlight);
  color: #FFF;
  padding: 10px 18px;
  border-radius: 100px;
  font-size: 12.5px;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  z-index: 300;
  pointer-events: none;
  animation: toastPop 0.25s ease;
}

@keyframes toastPop {
  from { opacity: 0; transform: translate(-50%, -10px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}

/* ==========================================================================
   SVG Vector Icons
   ========================================================================== */

.svg-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.svg-icon svg {
  display: block;
}

/* ==========================================================================
   Language Selector & Utility Buttons
   ========================================================================== */

.lang-selector {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.lang-btn {
  flex: 1;
  height: 36px;
  border-radius: 100px;
  background: #141620;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-family: var(--font);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lang-btn:active {
  transform: scale(0.96);
}

.lang-btn.is-selected {
  background: #18261E;
  color: var(--brand);
  border-color: rgba(33, 234, 124, 0.35);
  font-weight: 700;
}

.quick-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 14px;
  border-radius: 12px;
  background: #141620;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-family: var(--font);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.quick-btn:active {
  background: #181B26;
  color: #FFF;
}

/* ==========================================================================
   Executive Minimalist Header (v7.2 Refined)
   ========================================================================== */

.top-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(var(--tg-safe-top, 6px) + 6px) 16px 8px 16px;
  background: rgba(10, 11, 14, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid var(--border);
}

.header-brand-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.header-brand-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
  flex-shrink: 0;
}

.header-brand-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.header-brand-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.25;
}

.header-brand-sub {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.02em;
  line-height: 1.2;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.status-capsule-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border-radius: 100px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  border: 1px solid transparent;
}

.status-capsule-btn.is-online {
  background: rgba(33, 234, 124, 0.10);
  border-color: rgba(33, 234, 124, 0.28);
  color: var(--brand);
}

.status-capsule-btn.is-offline {
  background: rgba(239, 68, 68, 0.10);
  border-color: rgba(239, 68, 68, 0.28);
  color: var(--crimson);
}

.status-beacon-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
}

.status-text {
  font-size: 11.5px;
  font-weight: 700;
}

/* ==========================================================================
   Menu & Dishes Grid (Pixel-Perfect Luxury Cards)
   ========================================================================== */

.menu-top-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 10px 16px;
  gap: 10px;
}

.menu-cats-scroll {
  display: flex;
  gap: 6px;
  padding: 0 16px 8px 16px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.menu-cats-scroll::-webkit-scrollbar {
  display: none;
}

.cat-pill-count {
  font-size: 10px;
  opacity: 0.75;
  margin-left: 2px;
}

.dish-card-rich, .dish-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 12px 14px;
  margin: 0 16px 10px 16px;
  display: flex;
  gap: 14px;
  align-items: flex-start;
  transition: border-color 0.2s ease, opacity 0.2s ease;
}

.dish-card-rich.is-stopped, .dish-card.is-stopped {
  opacity: 0.60;
  border-color: rgba(239, 68, 68, 0.22);
}

.dish-img-box {
  width: 82px;
  height: 82px;
  min-width: 82px;
  max-width: 82px;
  border-radius: 14px;
  overflow: hidden;
  position: relative;
  background: #141620;
  border: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.dish-img-photo, .dish-img {
  width: 100% !important;
  height: 100% !important;
  max-width: 82px !important;
  max-height: 82px !important;
  object-fit: cover !important;
  display: block !important;
}

.dish-img-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: #151822;
}

.stock-tag {
  position: absolute;
  bottom: 4px;
  left: 4px;
  right: 4px;
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-align: center;
  padding: 2px 0;
  border-radius: 6px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.stock-tag.in-stock {
  background: rgba(14, 18, 16, 0.85);
  color: var(--brand);
  border: 1px solid rgba(33, 234, 124, 0.35);
}

.stock-tag.stopped {
  background: rgba(24, 12, 14, 0.85);
  color: var(--crimson);
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.dish-body-rich, .dish-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.dish-title-rich, .dish-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.dish-price-rich, .dish-price {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 800;
  color: var(--brand);
  white-space: nowrap;
  flex-shrink: 0;
}

.dish-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 5px;
}

.badge-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  background: #161824;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 2px 7px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.badge-tag.weight {
  color: var(--text-muted);
}

.dish-desc-rich {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.dish-footer-rich {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.btn-edit-dish {
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  background: #151822;
  border: 1px solid var(--border);
  color: #94A3B8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: all 0.2s ease;
}

.btn-edit-dish:active {
  background: #1c202d;
  color: #FFF;
}

/* ==========================================================================
   Statistics Hub (Charts, Top Dishes, Financial Settlement)
   ========================================================================== */

.bar-cylinder {
  width: 100%;
  max-width: 24px;
  border-radius: 6px 6px 4px 4px;
  background: #171924;
  transition: height 0.3s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.2s ease;
  min-height: 4px;
}

.bar-cylinder.has-sales {
  background: linear-gradient(180deg, #21EA7C 0%, #10B981 100%);
  box-shadow: 0 2px 8px rgba(33, 234, 124, 0.25);
}

.bar-cylinder.is-peak {
  background: linear-gradient(180deg, #38BDF8 0%, #0284C7 100%);
  box-shadow: 0 2px 8px rgba(56, 189, 248, 0.3);
}

.bar-day-lbl {
  font-size: 9.5px;
  font-weight: 600;
  color: var(--text-muted);
  text-align: center;
  white-space: nowrap;
}

.top-dishes-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  margin: 0 16px 12px 16px;
}

.top-dish-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.top-dish-row:last-child {
  border-bottom: none;
  padding-bottom: 2px;
}

.top-rank-circle {
  width: 26px;
  height: 26px;
  min-width: 26px;
  border-radius: 50%;
  background: #181B26;
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
  color: var(--text-secondary);
}

.top-rank-circle.gold {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.4);
  color: #F59E0B;
}

.top-dish-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 170px;
}

.top-dish-qty {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}

.top-dish-money {
  font-family: var(--font-display);
  font-size: 14.5px;
  font-weight: 800;
  color: var(--brand);
  white-space: nowrap;
}

.settlement-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  margin: 0 16px 20px 16px;
}

.settlement-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.settlement-row.total {
  border-top: 1px solid var(--border-highlight);
  border-bottom: none;
  margin-top: 6px;
  padding-top: 12px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

/* ==========================================================================
   Auxiliary Components (Client, Courier Trips, Timeline, Modals, Login)
   ========================================================================== */

.client-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  background: #141620;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  margin-top: 10px;
}

.client-info {
  min-width: 0;
}

.client-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.client-phone {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 1px;
}

.client-call-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 100px;
  background: rgba(33, 234, 124, 0.12);
  border: 1px solid rgba(33, 234, 124, 0.28);
  color: var(--brand);
  font-size: 11.5px;
  font-weight: 700;
  text-decoration: none;
}

.courier-trips-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.courier-trip-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: #141620;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
}

.courier-trip-route {
  min-width: 0;
}

.courier-trip-id {
  font-size: 11px;
  font-weight: 800;
  color: var(--brand);
}

.courier-trip-path {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.courier-trip-payout {
  font-family: var(--font-display);
  font-size: 14.5px;
  font-weight: 800;
  color: var(--brand);
  white-space: nowrap;
}

.stepper-step {
  display: flex;
  align-items: center;
  gap: 10px;
}

.timeline-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  margin-bottom: 12px;
}

.timeline-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
}

/* .details-content padding handled by modern block */

.details-share-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #161822;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.modal-sheet {
  background: #141620;
  border: 1px solid var(--border-highlight);
  border-radius: 24px 24px 0 0;
  padding: 20px 16px;
  width: 100%;
}

.modal-form-group {
  margin-bottom: 14px;
}

.modal-label {
  display: block;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.modal-textarea {
  width: 100%;
  height: 80px;
  background: #0E1017;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  color: #FFF;
  font-family: var(--font);
  font-size: 13px;
  resize: none;
}

.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.login-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 28px 24px;
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-field {
  width: 100%;
  height: 46px;
  background: #0D0F15;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0 14px;
  color: #FFF;
  font-family: var(--font);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s ease;
}
.input-field:focus {
  border-color: var(--brand);
}

.dish-grid-rich {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
}

.dish-toggle-switch {
  opacity: 0;
  width: 0;
  height: 0;
}

.courier-info-box.is-assigned {
  background: rgba(33, 234, 124, 0.06);
  border-color: rgba(33, 234, 124, 0.22);
}

.courier-info-box.is-waiting {
  background: rgba(245, 158, 11, 0.06);
  border-color: rgba(245, 158, 11, 0.22);
}

/* ==========================================================================
   Refined Search & Add Dish Button (Solid Luxury, Zero Dashed Border)
   ========================================================================== */

.menu-top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 8px 16px;
}

.search-box {
  flex: 1;
  height: 42px;
  background: #12141C;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: border-color 0.2s ease;
}

.search-box:focus-within {
  border-color: var(--brand-border);
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #FFF;
  font-family: var(--font);
  font-size: 13.5px;
  outline: none;
}

.btn-add-dish-primary {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  height: 42px !important;
  padding: 0 15px !important;
  border-radius: 12px !important;
  background: var(--brand) !important;
  color: #041208 !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  font-weight: 800 !important;
  border: none !important;
  cursor: pointer !important;
  box-shadow: 0 2px 12px rgba(33, 234, 124, 0.25) !important;
  white-space: nowrap !important;
  flex-shrink: 0 !important;
  margin: 0 !important;
  transition: transform 0.15s ease, filter 0.15s ease !important;
}

.btn-add-dish-primary:active {
  transform: scale(0.96) !important;
  filter: brightness(0.95) !important;
}

/* ==========================================================================
   Order Details View — Minimalist Luxury Terminal (v8.1)
   Full-width 16px edge-aligned layout, executive icon header & unified cards
   ========================================================================== */

.details-view {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text-primary);
  z-index: 120;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 0 !important;
  margin: 0 !important;
}

.details-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(var(--tg-safe-top, 8px) + 8px) 16px 12px 16px;
  background: rgba(10, 11, 14, 0.88);
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  position: sticky;
  top: 0;
  z-index: 60;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  gap: 12px;
}

.details-back-icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #E2E8F0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.details-back-icon-btn:active {
  transform: scale(0.94);
  background: rgba(255, 255, 255, 0.1);
  color: #FFFFFF;
}

.details-header-title-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  min-width: 0;
  flex: 1;
}

.details-header-title {
  font-family: var(--font-display);
  font-size: 16.5px;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: -0.01em;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.details-header-subtitle {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  margin-top: 2px;
  white-space: nowrap;
}

.details-icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94A3B8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.details-icon-btn:active {
  transform: scale(0.94);
  background: rgba(255, 255, 255, 0.1);
  color: #FFFFFF;
}

.details-content {
  padding: 14px 0 calc(var(--tg-safe-bottom, 24px) + 36px) 0 !important;
  width: 100%;
  box-sizing: border-box;
}

.details-card {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 20px !important;
  padding: 16px 18px !important;
  margin: 0 16px 14px 16px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  box-sizing: border-box;
}

.details-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.details-card-title {
  font-family: var(--font-display);
  font-size: 11.5px;
  font-weight: 800;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.details-status-badge {
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.details-status-badge.is-assigned {
  color: var(--sky);
}

.details-status-badge.is-searching {
  color: var(--text-muted);
}

.details-badge-muted {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}

.courier-search-text {
  font-size: 12.5px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* Timeline Stepper */
.order-stepper {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-top: 6px;
  position: relative;
}

.stepper-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex: 1;
  position: relative;
  z-index: 2;
}

.step-circle {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #141722;
  border: 1px solid var(--border);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
  transition: all 0.2s ease;
}

.stepper-step.is-active .step-circle {
  background: rgba(33, 234, 124, 0.15);
  border-color: var(--brand);
  color: var(--brand);
  box-shadow: 0 0 10px rgba(33, 234, 124, 0.25);
}

.stepper-step.is-done .step-circle {
  background: var(--brand);
  border-color: var(--brand);
  color: #041208;
}

.step-label {
  font-size: 9.5px;
  font-weight: 600;
  color: var(--text-muted);
  text-align: center;
  white-space: nowrap;
}

.stepper-step.is-active .step-label {
  color: var(--brand);
  font-weight: 700;
}

.stepper-step.is-done .step-label {
  color: var(--text-secondary);
}

.step-line {
  flex: 1;
  height: 2px;
  background: #1C1F2B;
  margin-top: 12px;
  margin-left: -4px;
  margin-right: -4px;
  position: relative;
  z-index: 1;
}

.step-line.is-done {
  background: var(--brand);
}

/* Order Totals Summary Box */
.order-totals-box {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 12px;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.totals-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-secondary);
}

.totals-val {
  font-weight: 600;
  color: var(--text-primary);
}

.totals-line.totals-main {
  padding-top: 10px;
  margin-top: 4px;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
}

.totals-main-label {
  font-size: 15px;
  font-weight: 800;
  color: #FFFFFF;
}

.totals-main-val {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 800;
  color: var(--brand);
}

/* Details Action Buttons */
.details-actions-wrap {
  margin: 18px 16px 0 16px !important;
  padding-bottom: calc(var(--tg-safe-bottom, 24px) + 16px);
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-sizing: border-box;
}

.btn-primary-action {
  width: 100%;
  height: 50px;
  border-radius: 14px;
  background: var(--brand);
  color: #041208;
  border: none;
  font-family: var(--font);
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0.01em;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: transform 0.15s ease, filter 0.15s ease, box-shadow 0.15s ease;
  box-shadow: 0 4px 16px rgba(33, 234, 124, 0.25);
}

.btn-primary-action:active {
  transform: scale(0.98);
  filter: brightness(0.95);
}

.btn-primary-action.state-cook {
  background: linear-gradient(135deg, #38BDF8 0%, #0284C7 100%);
  color: #041424;
  box-shadow: 0 4px 16px rgba(56, 189, 248, 0.25);
}

.btn-primary-action.state-ready {
  background: linear-gradient(135deg, #21EA7C 0%, #10B981 100%);
  color: #041208;
  box-shadow: 0 4px 16px rgba(33, 234, 124, 0.28);
}

.btn-secondary-danger {
  width: 100%;
  height: 44px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.06);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.24);
  font-family: var(--font);
  font-size: 13.5px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s ease;
}

.btn-secondary-danger:active {
  background: rgba(239, 68, 68, 0.12);
  transform: scale(0.98);
}

/* Profile Hero Card (Executive, No Avatar) */
.profile-hero-card {
  padding: 16px 18px !important;
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 18px !important;
  margin: 0 16px 14px 16px !important;
}

.profile-hero-title {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: -0.01em;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.profile-hero-subtitle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* ==========================================================================
   MestiDelivery Partners v7.4 — Minimalist Luxury Tier-1 Refinement
   Signature Floating Matte Glass Navbar & Executive Account Architecture
   ========================================================================== */

/* 1. Global Floating Matte Glass Navbar (Direct from MestiDelivery Client App) */
.bottom-nav {
  position: fixed !important;
  bottom: calc(14px + env(safe-area-inset-bottom, 0px)) !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
  width: calc(100% - 32px) !important;
  max-width: 360px !important;
  height: 64px !important;
  border-radius: 36px !important;
  background: rgba(16, 18, 24, 0.86) !important;
  backdrop-filter: blur(24px) saturate(160%) !important;
  -webkit-backdrop-filter: blur(24px) saturate(160%) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.12), 0 16px 40px rgba(0, 0, 0, 0.65) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: space-around !important;
  padding: 0 8px !important;
  z-index: 1000 !important;
}

.tab-btn {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 3px !important;
  background: transparent !important;
  border: none !important;
  color: #71717A !important;
  cursor: pointer !important;
  position: relative !important;
  padding: 6px 12px !important;
  border-radius: 20px !important;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

.tab-btn:active {
  transform: scale(0.92) !important;
}

.tab-btn.is-active {
  color: var(--brand) !important;
}

.tab-btn.is-active svg {
  filter: drop-shadow(0 0 8px rgba(33, 234, 124, 0.45)) !important;
}

.tab-btn.is-active::after {
  content: '' !important;
  position: absolute !important;
  bottom: 1px !important;
  width: 4px !important;
  height: 4px !important;
  border-radius: 50% !important;
  background: var(--brand) !important;
  box-shadow: 0 0 6px var(--brand) !important;
}

.tab-label {
  font-size: 10.5px !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
}

/* 2. Executive Account Card (Zero Redundant Titles or Duplicate Buttons) */
.profile-account-card {
  margin: 0 16px 16px 16px !important;
  padding: 16px 18px !important;
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 18px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  gap: 12px !important;
}

.account-details-col {
  min-width: 0 !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 2px !important;
}

.account-eyebrow {
  font-size: 10px !important;
  font-weight: 800 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--brand) !important;
}

.account-username {
  font-family: var(--font-display) !important;
  font-size: 16.5px !important;
  font-weight: 800 !important;
  color: #FFFFFF !important;
  letter-spacing: -0.01em !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

.account-sub {
  font-size: 11.5px !important;
  color: var(--text-muted) !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

.account-role-pill {
  padding: 6px 12px !important;
  border-radius: 100px !important;
  background: rgba(255, 255, 255, 0.04) !important;
  border: 1px solid var(--border) !important;
  font-size: 11.5px !important;
  font-weight: 700 !important;
  color: var(--text-secondary) !important;
  display: flex !important;
  align-items: center !important;
  gap: 6px !important;
  flex-shrink: 0 !important;
}

/* 3. Sleek Apple-style Segmented Control (Zero Gimmick Clocks/Zaps) */
.segmented-control {
  display: flex !important;
  background: #0D0F14 !important;
  border-radius: 12px !important;
  padding: 3px !important;
  gap: 3px !important;
  border: 1px solid rgba(255, 255, 255, 0.06) !important;
  width: 100% !important;
  box-sizing: border-box !important;
}

.segment-btn {
  flex: 1 !important;
  height: 36px !important;
  border-radius: 9px !important;
  background: transparent !important;
  border: none !important;
  color: var(--text-muted) !important;
  font-family: var(--font) !important;
  font-size: 12.5px !important;
  font-weight: 700 !important;
  cursor: pointer !important;
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  white-space: nowrap !important;
}

.segment-btn:active {
  transform: scale(0.97) !important;
}

.segment-btn.is-active {
  background: #1B1E29 !important;
  color: var(--brand) !important;
  border: 1px solid rgba(33, 234, 124, 0.25) !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4) !important;
}

/* 4. Refined Settings Rows & Clean Buttons */
.btn-test-sound-sm {
  height: 28px !important;
  padding: 0 10px !important;
  border-radius: 8px !important;
  background: #161822 !important;
  border: 1px solid var(--border) !important;
  color: var(--text-secondary) !important;
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 4px !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
}

.btn-test-sound-sm:active {
  background: #1F2333 !important;
  color: #FFF !important;
}

.btn-clean-secondary {
  width: 100% !important;
  height: 42px !important;
  border-radius: 12px !important;
  background: #13151D !important;
  border: 1px solid var(--border) !important;
  color: #94A3B8 !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 8px !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
}

.btn-clean-secondary:active {
  background: #1A1D28 !important;
  color: #FFF !important;
}

.btn-clean-danger {
  width: 100% !important;
  height: 42px !important;
  border-radius: 12px !important;
  background: rgba(239, 68, 68, 0.05) !important;
  border: 1px solid rgba(239, 68, 68, 0.18) !important;
  color: #EF4444 !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
}

.btn-clean-danger:active {
  background: rgba(239, 68, 68, 0.12) !important;
}

.app-version-footnote {
  text-align: center !important;
  font-size: 11px !important;
  color: var(--text-muted) !important;
  letter-spacing: 0.02em !important;
  margin-top: 4px !important;
}

/* 5. Safe Area Container Spacing for Floating Navbar */
.feed-container,
.details-content,
.dish-grid-rich {
  padding-bottom: 120px !important;
}

/* Header & Profile Avatar Components */
.header-user-avatar-wrap {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: linear-gradient(135deg, #1E293B, #0F172A);
  border: 1.5px solid rgba(56, 189, 248, 0.35);
}

.header-user-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.header-user-avatar-initials {
  font-size: 14px;
  font-weight: 700;
  color: #38BDF8;
  text-transform: uppercase;
  user-select: none;
}

.account-avatar-wrap {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: linear-gradient(135deg, #1E293B, #0F172A);
  border: 1.5px solid rgba(56, 189, 248, 0.3);
}

.account-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.account-avatar-initials {
  font-size: 17px;
  font-weight: 700;
  color: #38BDF8;
  text-transform: uppercase;
  user-select: none;
}

.profile-meta-footnote {
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 14px;
  padding-bottom: 20px;
  letter-spacing: 0.02em;
  user-select: none;
}


/* ==========================================================================
   Cyber-Luxe Frosted Glass Top Header (v7.7 Apple/Mesti Standard)
   ========================================================================== */

.top-header {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  padding: calc(var(--tg-safe-top, 8px) + 8px) 16px 12px 16px !important;
  background: rgba(10, 11, 14, 0.85) !important;
  backdrop-filter: blur(28px) saturate(180%) !important;
  -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
  position: sticky !important;
  top: 0 !important;
  z-index: 50 !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35) !important;
}

.header-brand-wrap {
  display: flex !important;
  align-items: center !important;
  gap: 12px !important;
  min-width: 0 !important;
}

/* Frosted Identity Container: Squircle for Kitchen, Circle for Courier */
.header-identity-box {
  width: 38px !important;
  height: 38px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex-shrink: 0 !important;
  background: rgba(255, 255, 255, 0.04) !important;
  border: 1px solid rgba(255, 255, 255, 0.10) !important;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.12) !important;
  overflow: hidden !important;
}

.header-identity-box.kitchen-mode {
  border-radius: 11px !important;
}

.header-identity-box.courier-mode {
  border-radius: 50% !important;
  border-color: rgba(33, 234, 124, 0.35) !important;
}

.header-identity-logo {
  width: 22px !important;
  height: 22px !important;
  object-fit: contain !important;
  filter: drop-shadow(0 0 6px rgba(33, 234, 124, 0.45)) !important;
}

.header-identity-img {
  width: 100% !important;
  height: 100% !important;
  object-fit: cover !important;
}

.header-identity-initials {
  font-family: var(--font-display) !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  color: var(--brand) !important;
  line-height: 1 !important;
}

.header-brand-meta {
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  min-width: 0 !important;
  gap: 2px !important;
}

.header-brand-title {
  font-family: "Outfit", var(--font-display), sans-serif !important;
  font-size: 15.5px !important;
  font-weight: 700 !important;
  color: #FFFFFF !important;
  letter-spacing: -0.015em !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  line-height: 1.2 !important;
}

.header-brand-subtitle {
  font-size: 11px !important;
  font-weight: 500 !important;
  color: #7E8695 !important;
  letter-spacing: 0.01em !important;
  line-height: 1.2 !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

.header-actions {
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  flex-shrink: 0 !important;
}

/* Tactile Frosted Glass Status Pill */
.status-capsule-btn {
  display: inline-flex !important;
  align-items: center !important;
  gap: 7px !important;
  height: 30px !important;
  padding: 0 12px !important;
  border-radius: 9999px !important;
  font-family: var(--font) !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
  text-transform: none !important;
  cursor: pointer !important;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
  border: 1px solid transparent !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  user-select: none !important;
  -webkit-user-select: none !important;
}

.status-capsule-btn:active {
  transform: scale(0.95) !important;
}

.status-capsule-btn.is-online {
  background: rgba(33, 234, 124, 0.08) !important;
  border-color: rgba(33, 234, 124, 0.22) !important;
  color: #21EA7C !important;
  box-shadow: 0 2px 8px rgba(33, 234, 124, 0.06) !important;
}

.status-capsule-btn.is-offline {
  background: rgba(255, 255, 255, 0.04) !important;
  border-color: rgba(255, 255, 255, 0.08) !important;
  color: #8E95A5 !important;
  box-shadow: none !important;
}

.status-beacon-dot {
  width: 6px !important;
  height: 6px !important;
  border-radius: 50% !important;
  flex-shrink: 0 !important;
  transition: all 0.2s ease !important;
}

.status-capsule-btn.is-online .status-beacon-dot {
  background: #21EA7C !important;
  box-shadow: 0 0 8px #21EA7C, 0 0 2px #21EA7C !important;
  animation: statusBeaconPulse 2s infinite ease-in-out !important;
}

.status-capsule-btn.is-offline .status-beacon-dot {
  background: #64748B !important;
  box-shadow: none !important;
  animation: none !important;
}

@keyframes statusBeaconPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.85); }
}

.status-text {
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
  line-height: 1 !important;
}

/* Menu Top Actions & Spacing with Comfortable Breathing Room */
.menu-top-actions {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  padding: 12px 16px 10px 16px !important;
}

.menu-cats-scroll {
  display: flex !important;
  gap: 6px !important;
  padding: 0 16px 18px 16px !important; /* Comfortable breathing room ("воздух") */
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch !important;
}
.menu-cats-scroll::-webkit-scrollbar {
  display: none !important;
}

.dish-card-rich, .dish-card {
  margin: 0 16px 12px 16px !important;
}

/* ==========================================================================
   Kitchen Mini Card — Ultra-Legible Operational Layout (v7.8)
   ========================================================================== */

.card {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 20px !important;
  padding: 16px 16px 14px 16px !important;
  margin: 0 16px 14px 16px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important;
  transition: transform 0.15s ease, border-color 0.15s ease !important;
}

.card-header {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  padding-bottom: 12px !important;
  margin-bottom: 12px !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.card-title-wrap {
  display: flex !important;
  align-items: baseline !important;
  gap: 8px !important;
}

.order-id {
  font-family: "Outfit", var(--font-display), sans-serif !important;
  font-size: 16px !important;
  font-weight: 700 !important;
  color: #FFFFFF !important;
  letter-spacing: -0.015em !important;
}

.order-elapsed {
  font-size: 12px !important;
  color: #7E8695 !important;
  font-weight: 500 !important;
}

/* Items List */
.items-table {
  display: flex !important;
  flex-direction: column !important;
  gap: 9px !important;
  margin-bottom: 12px !important;
}

.item-line {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  gap: 12px !important;
}

.item-left {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  min-width: 0 !important;
  flex: 1 !important;
}

.item-qty-badge {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 28px !important;
  height: 24px !important;
  padding: 0 6px !important;
  border-radius: 6px !important;
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  color: #E2E8F0 !important;
  font-family: "Outfit", var(--font-display), sans-serif !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  letter-spacing: -0.01em !important;
  flex-shrink: 0 !important;
}

/* Eye-catching badge when kitchen has to prepare >1 portions */
.item-qty-badge.is-multi {
  background: rgba(33, 234, 124, 0.12) !important;
  border-color: rgba(33, 234, 124, 0.30) !important;
  color: #21EA7C !important;
}

.item-title {
  font-size: 14.5px !important;
  font-weight: 600 !important;
  color: #F1F5F9 !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  letter-spacing: -0.01em !important;
  line-height: 1.3 !important;
}

.item-cost {
  font-family: "Outfit", var(--font-display), sans-serif !important;
  font-size: 13.5px !important;
  font-weight: 600 !important;
  color: #8E95A5 !important;
  flex-shrink: 0 !important;
}

.items-more-link {
  font-size: 12px !important;
  font-weight: 600 !important;
  color: #38BDF8 !important;
  margin-top: 4px !important;
  cursor: pointer !important;
  display: inline-block !important;
}

/* Card Summary Row */
.card-summary {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  padding: 12px 0 14px 0 !important;
  margin-top: 4px !important;
  border-top: 1px solid rgba(255, 255, 255, 0.06) !important;
}

.card-summary .summary-label {
  font-size: 12.5px !important;
  font-weight: 500 !important;
  color: #8E95A5 !important;
  text-transform: none !important;
  letter-spacing: 0 !important;
}

.total-amount {
  font-family: "Outfit", var(--font-display), sans-serif !important;
  font-size: 18px !important;
  font-weight: 800 !important;
  color: #FFFFFF !important;
  letter-spacing: -0.01em !important;
}

/* ==========================================================================
   Modals & Dynamic Floating Navbar Visibility (v7.9)
   ========================================================================== */

/* Hide bottom navigation when any modal is open */
body.modal-open .bottom-nav,
body:has(.modal-backdrop) .bottom-nav,
.modal-open .bottom-nav,
.bottom-nav.is-hidden {
  display: none !important;
  pointer-events: none !important;
  opacity: 0 !important;
  visibility: hidden !important;
}

body.modal-open {
  overflow: hidden !important;
}

/* Precision styling for Modal Backdrop & Sheet */
.modal-backdrop {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  background: rgba(0, 0, 0, 0.78) !important;
  backdrop-filter: blur(16px) !important;
  -webkit-backdrop-filter: blur(16px) !important;
  z-index: 9999 !important;
  display: flex !important;
  align-items: flex-end !important;
  justify-content: center !important;
  padding: 0 !important;
}

.modal-sheet {
  position: relative !important;
  z-index: 10000 !important;
  background: var(--surface) !important;
  border: 1px solid var(--border-highlight) !important;
  border-radius: 28px 28px 0 0 !important;
  padding: 22px 18px calc(28px + env(safe-area-inset-bottom, 16px)) 18px !important;
  width: 100% !important;
  max-width: 500px !important;
  max-height: 90vh !important;
  overflow-y: auto !important;
  -webkit-overflow-scrolling: touch !important;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.75) !important;
}

.modal-actions-row {
  display: flex !important;
  gap: 10px !important;
  margin-top: 24px !important;
  padding-bottom: 10px !important;
}

/* ==========================================================================
   Tabbar Clean Architecture (v8.0) — Zero Underline Dots, Pure Icon Glow
   ========================================================================== */

.tab-btn {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  background: transparent !important;
  border: none !important;
  color: #71717A !important;
  cursor: pointer !important;
  position: relative !important;
  padding: 8px 12px !important;
  transition: color 0.18s ease, transform 0.18s ease !important;
}

.tab-btn:active {
  transform: scale(0.92) !important;
}

.tab-btn.is-active {
  color: var(--brand) !important;
}

.tab-btn.is-active svg {
  filter: drop-shadow(0 0 6px rgba(33, 234, 124, 0.45)) !important;
  transform: translateY(-1px) !important;
}

/* Completely eliminate underline dot on active tab */
.tab-btn.is-active::after,
.tab-btn::after {
  display: none !important;
  content: none !important;
  width: 0 !important;
  height: 0 !important;
  opacity: 0 !important;
}

.tab-label {
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
  line-height: 1 !important;
}

.app-version-footnote {
  text-align: center !important;
  font-size: 11px !important;
  color: var(--text-muted) !important;
  letter-spacing: 0.02em !important;
  margin-top: 8px !important;
}
`;

  function ensureStyles() {
    if (!document.getElementById('partners-core-styles')) {
      const styleEl = document.createElement('style');
      styleEl.id = 'partners-core-styles';
      styleEl.textContent = EMBEDDED_CSS;
      document.head.appendChild(styleEl);
    }
  }
  ensureStyles();

  // SVG Icon System — Sharp, Vector-Crisp, Pixel-Perfect
  function renderCourierAvatar(photoUrl, name, size = 26) {
    const cleanName = (name || 'К').trim();
    const initial = cleanName.charAt(0).toUpperCase() || 'К';
    const photo = photoUrl ? String(photoUrl).trim() : '';

    if (photo) {
      return `
        <div class="courier-avatar-container" style="width: ${size}px; height: ${size}px;">
          <img src="${photo}" alt="${cleanName}" class="courier-avatar-img" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
          <div class="courier-avatar-fallback" style="display: none; width: ${size}px; height: ${size}px; font-size: ${Math.round(size * 0.44)}px;">${initial}</div>
        </div>
      `;
    }

    return `
      <div class="courier-avatar-container" style="width: ${size}px; height: ${size}px;">
        <div class="courier-avatar-fallback" style="width: ${size}px; height: ${size}px; font-size: ${Math.round(size * 0.44)}px;">${initial}</div>
      </div>
    `;
  }

  function iconSvg(name, extraClass = '', size = 16) {
    const cls = ('svg-icon ' + (extraClass || '')).trim();
    const icons = {
      restaurant: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M3 10h18M5 10v11M19 10v11M9 10v11M15 10v11M4 10l8-6 8 6"/></svg>`,
      kitchen: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2v6a3 3 0 0 1-3 3 3 3 0 0 1-3-3V2M15 11v11M5 2v10M5 12h3a3 3 0 0 0 3-3V2"/></svg>`,
      plus: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
      copy: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
      scooter: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 18h4l3-8 4 2M15 6h4M17 6l-2 4M9 18l1-5h4"/></svg>`,
      courier: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 18h4l3-8 4 2M15 6h4M17 6l-2 4M9 18l1-5h4"/></svg>`,
      bell: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>`,
      'bell-off': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5M17 17H3s3-2 3-9a4.67 4.67 0 0 1 .3-1.7M10.3 21a1.94 1.94 0 0 0 3.4 0M2 2l20 20"/></svg>`,
      pin: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`,
      home: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
      phone: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>`,
      clock: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
      package: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m16.5 9.4-9-5.19M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
      check: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
      cross: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>`,
      map: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>`,
      wallet: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg>`,
      settings: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
      zap: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
      headset: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>`,
      shield: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
      'file-text': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
      'transport-foot': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13" cy="4" r="2"/><path d="m9 20 3-6 2 3 3 3M6 13l3-3 4 1 3 4M10 10l-1 5-4 1"/></svg>`,
      'transport-bike': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/></svg>`,
      'transport-scooter': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 18h4l3-8 4 2M15 6h4M17 6l-2 4M9 18l1-5h4"/></svg>`,
      'transport-car': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.5 2.8C2.1 10.7 2 11 2 11.4V16c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>`,
      scale: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10M12 3v18M3 7h18"/></svg>`,
      tag: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/><circle cx="7" cy="7" r=".5" fill="currentColor"/></svg>`,
      globe: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
      refresh: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M3 21v-5h5"/></svg>`,
      radar: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 4a6 6 0 1 0 6 6 6 6 0 0 0-6-6Zm0 4a2 2 0 1 0 2 2 2 2 0 0 0-2-2Z"/><path d="M12 12 19 5"/></svg>`,
      alert: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
      sparkle: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>`,
      soup: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21a9 9 0 0 0 9-9H3a9 9 0 0 0 9 9Z"/><path d="M7 8V3M12 8V3M17 8V3"/></svg>`,
      arrowRight: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`
    };
    const svgContent = icons[name] || icons['package'];
    return `<span class="${cls}">${svgContent}</span>`;
  }


  // 2. Safe Local Storage
  const memoryStore = {};
  const safeStorage = {
    get(key, fallback = null) {
      try {
        const val = window.localStorage ? window.localStorage.getItem(key) : null;
        return val !== null ? val : fallback;
      } catch (e) {
        return memoryStore[key] !== undefined ? memoryStore[key] : fallback;
      }
    },
    set(key, val) {
      try {
        if (window.localStorage) window.localStorage.setItem(key, val);
      } catch (e) {
        memoryStore[key] = val;
      }
    },
    remove(key) {
      try {
        if (window.localStorage) window.localStorage.removeItem(key);
      } catch (e) {
        delete memoryStore[key];
      }
    },
    clear() {
      try {
        if (window.localStorage) window.localStorage.clear();
      } catch (e) {}
    }
  };

  // 3. Telegram WebApp Bridge & Safe Areas
  function getTG() {
    return window.Telegram?.WebApp || null;
  }

  function applySafeAreas() {
    const tg = getTG();
    const platform = (tg?.platform || '').toLowerCase();
    const isMobile = platform === 'ios' || platform === 'android';
    let topInset = isMobile ? 12 : 4;
    let bottomInset = isMobile ? 18 : 6;

    if (tg) {
      try {
        tg.ready();
        tg.expand();

        if (typeof tg.requestFullscreen === 'function') {
          tg.requestFullscreen();
        }

        if (typeof tg.disableVerticalSwipes === 'function') {
          tg.disableVerticalSwipes();
        }
        if (typeof tg.enableClosingConfirmation === 'function') {
          tg.enableClosingConfirmation();
        }
      } catch (e) {}

      if (tg.safeAreaInset) {
        topInset = Math.max(topInset, tg.safeAreaInset.top || 0);
        bottomInset = Math.max(bottomInset, tg.safeAreaInset.bottom || 0);
      }
      if (tg.contentSafeAreaInset) {
        topInset = Math.max(topInset, tg.contentSafeAreaInset.top || 0);
        bottomInset = Math.max(bottomInset, tg.contentSafeAreaInset.bottom || 0);
      }
    }

    document.documentElement.style.setProperty('--tg-safe-top', `${topInset}px`);
    document.documentElement.style.setProperty('--tg-safe-bottom', `${bottomInset}px`);
  }

  applySafeAreas();
  const tgRef = getTG();
  if (tgRef) {
    tgRef.onEvent?.('safeAreaChanged', applySafeAreas);
    tgRef.onEvent?.('contentSafeAreaChanged', applySafeAreas);
    tgRef.onEvent?.('viewportChanged', applySafeAreas);
  }

  function extractTelegramUser() {
    const tg = getTG();
    if (tg?.initDataUnsafe?.user) {
      return tg.initDataUnsafe.user;
    }
    try {
      const p = new URLSearchParams(window.location.search);
      const raw = p.get('tgWebAppData') || p.get('initData');
      if (raw) {
        const parsed = new URLSearchParams(raw);
        const u = parsed.get('user');
        if (u) return JSON.parse(decodeURIComponent(u));
      }
    } catch (e) {}
    return null;
  }

  // 4. Haptic Feedback
  function haptic(type = 'light') {
    if (!state.hapticEnabled) return;
    const tg = getTG();
    if (!tg?.HapticFeedback) return;
    try {
      if (type === 'light' || type === 'medium' || type === 'heavy') {
        tg.HapticFeedback.impactOccurred(type);
      } else if (type === 'success' || type === 'warning' || type === 'error') {
        tg.HapticFeedback.notificationOccurred(type);
      }
    } catch (e) {}
  }

  // 5. Audio Notifications
  let audioCtx = null;
  function playNewOrderChime() {
    if (!state.soundEnabled) return;
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      if (!audioCtx) audioCtx = new AudioContextClass();
      if (audioCtx.state === 'suspended') audioCtx.resume();

      const now = audioCtx.currentTime;
      const osc1 = audioCtx.createOscillator();
      const osc2 = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(523.25, now); // C5
      osc1.frequency.exponentialRampToValueAtTime(659.25, now + 0.12); // E5

      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(659.25, now + 0.12);
      osc2.frequency.exponentialRampToValueAtTime(783.99, now + 0.28); // G5

      gain.gain.setValueAtTime(0.01, now);
      gain.gain.linearRampToValueAtTime(0.35, now + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.55);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(audioCtx.destination);

      osc1.start(now);
      osc1.stop(now + 0.18);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.55);
    } catch (e) {}
  }

  // 6. Internationalization (RU / EN / KA)
  const I18N = {
    ru: {
      brand_sub: 'Среда для партнёров',
      online: 'На смене',
      offline: 'Перерыв',
      tab_orders: 'Заказы',
      tab_menu: 'Меню',
      tab_stats: 'Статистика',
      tab_profile: 'Профиль',
      sub_active: 'Активные',
      sub_history: 'История',
      sub_radar: 'Радар',
      sub_my: 'Мои доставки',
      stat_revenue: 'Выручка',
      stat_count: 'Заказов',
      stat_avg: 'Ср. чек',
      order_hash: 'Заказ #',
      note_prefix: 'Примечание к заказу:',
      total_prefix: 'Сумма заказа:',
      search_placeholder: 'Поиск по номеру #, блюду...',
      filter_all: 'Все',
      filter_new: 'Новые',
      filter_cooking: 'Готовятся',
      filter_ready: 'Готовы',
      btn_open_details: 'Открыть подробности',
      details_title: 'Подробности заказа',
      details_back: 'Назад',
      details_copy_link: 'Скопировать ссылку',
      details_link_copied: 'Ссылка на заказ скопирована!',
      details_timeline: 'Статус выполнения',
      stage_created: 'Создан',
      stage_confirmed: 'Принят',
      stage_cooking: 'Кухня',
      stage_ready: 'Готов',
      stage_delivery: 'Доставка',
      stage_delivered: 'Доставлен',
      client_info_title: 'Клиент',
      btn_call: 'Позвонить',
      route_title: 'Маршрут доставки',
      btn_open_map: 'Открыть на карте',
      ticket_title: 'Состав заказа',
      ticket_subtotal: 'Сумма блюд:',
      ticket_delivery: 'Доставка:',
      status_new: 'Новый',
      status_pending: 'Новый',
      status_confirmed: 'Принят',
      status_accepted: 'Принят',
      status_preparing: 'Готовится',
      status_ready: 'Готов к выдаче',
      status_delivering: 'В пути',
      status_on_the_way: 'В пути',
      status_delivered: 'Доставлен',
      status_cancelled: 'Отменён',
      btn_accept: 'Принять заказ',
      btn_cancel: 'Отменить заказ',
      btn_cook: 'Начать готовить',
      btn_ready: 'Готово к выдаче',
      btn_take: 'Взять доставку',
      btn_pickup: 'Забрал заказ',
      btn_complete: 'Доставлено клиенту',
      btn_waiting_courier: 'Ожидание курьера',
      btn_waiting_kitchen: 'Ожидание кухни',
      empty_active: 'Нет активных заказов',
      empty_active_sub: 'Новые заказы появятся здесь моментально',
      empty_history: 'История пуста',
      empty_radar: 'Свободных заказов нет',
      empty_radar_sub: 'Ожидайте поступления заказов от заведений',
      empty_search: 'По запросу ничего не найдено',
      empty_menu: 'Позиции меню не найдены',
      not_reg_title: 'Аккаунт не зарегистрирован',
      not_reg_sub: 'Этот Telegram аккаунт ещё не привязан к системе партнёров MestiDelivery.',
      not_reg_btn: 'Перейти в бота @MestiDelivery_Robot',
      not_reg_or_login: 'Войти по логину и паролю',
      login_title: 'Вход для партнёров',
      login_sub: 'Используйте логин и пароль выданные администратором',
      login_btn: 'Войти в панель',
      lang_label: 'Язык интерфейса',
      logout: 'Выйти из аккаунта',
      sound_label: 'Звуковые оповещения',
      confirm_cancel: 'Вы уверены, что хотите отменить этот заказ?',
      // Courier Info
      courier_assigned_title: 'Курьер',
      courier_searching: 'Поиск курьера...',
      courier_waiting_title: 'Курьер подбирается',
      courier_waiting_sub: 'Платформа оповестит курьеров по готовности',
      courier_call: 'Позвонить',
      courier_status_enroute: 'Курьер едет за заказом',
      order_notes_title: 'Пожелания к заказу',
      // Menu Management
      menu_search_ph: 'Поиск по блюдам или составу...',
      menu_all_cats: 'Все',
      menu_stopped_cat: 'Стоп-лист',
      btn_add_dish: '+ Блюдо',
      dish_in_stock: 'В наличии',
      dish_stopped: 'В стоп-листе',
      btn_edit: 'Изменить',
      modal_edit_dish_title: 'Редактирование блюда',
      modal_add_dish_title: 'Новое блюдо в меню',
      field_name: 'Название блюда',
      field_price: 'Цена (₾)',
      field_category: 'Категория',
      field_weight: 'Граммовка / объем (напр. 250 г)',
      field_description: 'Описание блюда / состав',
      field_status: 'Статус доступности',
      btn_save: 'Сохранить',
      btn_cancel_modal: 'Отмена',
      dish_saved_toast: 'Блюдо успешно обновлено!',
      dish_created_toast: 'Блюдо добавлено в меню!',
      // Stats
      period_today: 'Сегодня',
      period_week: '7 дней',
      period_month: 'Месяц',
      period_all: 'Всё время',
      stats_title: 'Аналитика заведения',
      kpi_revenue: 'Выручка',
      kpi_delivered: 'Доставлено',
      kpi_active: 'В работе',
      kpi_avg_check: 'Средний чек',
      chart_sales_dynamic: 'Динамика продаж',
      top_dishes_title: 'Лидеры продаж',
      payout_title: 'Финансовый расчет',
      payout_rest_share: 'Выручка кухни (90%)',
      payout_platform_fee: 'Комиссия сервиса (10%)',
      payout_ready_status: 'Готово к расчету',
      // Profile Hub
      profile_hub_title: 'Панель управления',
      prep_time_title: 'Среднее время приготовления',
      auto_accept_title: 'Авто-приём заказов',
      auto_accept_sub: 'Сразу переводить новые заказы в статус "Принят"',
      sound_test_btn: 'Проверить звук гонга',
      haptic_title: 'Тактильный отклик',
      haptic_sub: 'Вибрация при кликах и изменениях статусов',
      schedule_title: 'График работы кухни',
      phone_admin_title: 'Телефон администратора кухни',
      support_dispatcher_btn: 'Связаться с диспетчером платформы',
      support_report_btn: 'Сообщить о проблеме с заказом',
      faq_title: 'Регламент и памятка для кухни',
      faq_q1: 'Стандарты упаковки блюд',
      faq_a1: 'Все соусы и супы должны быть упакованы в герметичные контейнеры. Горячие блюда упаковываются отдельно от холодных напитков и десертов. Пакет плотно запечатывается стикером с номером заказа.',
      faq_q2: 'Задержка приготовления (>10 мин)',
      faq_a2: 'Если кухня перегружена или задерживается, немедленно свяжитесь с диспетчером через кнопку выше. Это позволит предупредить клиента и курьера без штрафов и потери рейтинга заведения.',
      faq_q3: 'Закончилось блюдо или ингредиент',
      faq_a3: 'Перейдите во вкладку "Меню" и переключите блюдо в стоп-лист. Оно моментально перестанет отображаться клиентам в приложении.',
      faq_q4: 'Передача заказа курьеру',
      faq_a4: 'Всегда сверяйте номер заказа (например, #10024) с экраном телефона курьера перед передачей пакета. Имя и прямой контакт назначенного курьера доступны в карточке заказа.',
      btn_clear_cache: 'Очистить кэш и синхронизировать',
      cache_cleared_toast: 'Локальный кэш очищен, данные обновлены!',
      settings_saved_toast: 'Настройки заведения сохранены!',
      // Courier Keys
      tab_deliveries: 'Доставки',
      tab_earnings: 'Заработок',
      courier_kpi_earnings: 'Заработано',
      courier_kpi_deliveries: 'Доставок',
      courier_kpi_tips: 'Чаевые',
      courier_kpi_avg: 'Ср. рейс',
      courier_chart_title: 'Динамика доставок',
      courier_trips_title: 'Выполненные рейсы',
      courier_payout_title: 'Баланс и выплаты',
      courier_payout_ready: 'Доступно к выводу',
      courier_btn_withdraw: 'Запросить вывод средств',
      courier_transport_title: 'Транспорт доставки',
      courier_regulations_title: 'Регламент и памятка для курьера',
      courier_faq_q1: 'Стандарты термосумки и чистота',
      courier_faq_a1: 'Всегда используйте чистую термосумку. Супы и напитки перевозите строго вертикально в подстаканниках во избежание пролива. Горячие блюда изолируйте от холодных десертов.',
      courier_faq_q2: 'Навигация и прибытие к клиенту',
      courier_faq_a2: 'Внимательно проверяйте адрес доставки, номер подъезда, этаж и домофон. Если в комментарии нет пометки «Не звонить», наберите клиенту за 5 минут до прибытия.',
      courier_faq_q3: 'Сверка заказа на кухне',
      courier_faq_a3: 'При заборе заказа из ресторана сверяйте номер чека на пакете с номером в приложении. Ни в коем случае не вскрывайте герметичные пакеты и контейнеры.',
      courier_faq_q4: 'Задержки в пути и форс-мажоры',
      courier_faq_a4: 'При поломке транспорта, сильном снегопаде или трудностях с поиском адреса немедленно свяжитесь с диспетчером платформы через кнопку связи.'
    },
    en: {
      brand_sub: 'Partner Environment',
      online: 'Online',
      offline: 'Offline',
      tab_orders: 'Orders',
      tab_menu: 'Menu',
      tab_stats: 'Statistics',
      tab_profile: 'Profile',
      sub_active: 'Active',
      sub_history: 'History',
      sub_radar: 'Radar',
      sub_my: 'My Deliveries',
      stat_revenue: 'Revenue',
      stat_count: 'Orders',
      stat_avg: 'Avg Check',
      order_hash: 'Order #',
      note_prefix: 'Order note:',
      total_prefix: 'Total amount:',
      search_placeholder: 'Search by #, item...',
      filter_all: 'All',
      filter_new: 'New',
      filter_cooking: 'Cooking',
      filter_ready: 'Ready',
      btn_open_details: 'Open Details',
      details_title: 'Order Details',
      details_back: 'Back',
      details_copy_link: 'Copy Link',
      details_link_copied: 'Order link copied!',
      details_timeline: 'Order Progress',
      stage_created: 'Created',
      stage_confirmed: 'Confirmed',
      stage_cooking: 'Kitchen',
      stage_ready: 'Ready',
      stage_delivery: 'Delivery',
      stage_delivered: 'Delivered',
      client_info_title: 'Customer',
      btn_call: 'Call',
      route_title: 'Delivery Route',
      btn_open_map: 'Open in Maps',
      ticket_title: 'Order Items',
      ticket_subtotal: 'Items subtotal:',
      ticket_delivery: 'Delivery:',
      status_new: 'New',
      status_pending: 'New',
      status_confirmed: 'Confirmed',
      status_accepted: 'Confirmed',
      status_preparing: 'Cooking',
      status_ready: 'Ready',
      status_delivering: 'On Delivery',
      status_on_the_way: 'On Delivery',
      status_delivered: 'Delivered',
      status_cancelled: 'Cancelled',
      btn_accept: 'Accept Order',
      btn_cancel: 'Cancel Order',
      btn_cook: 'Start Cooking',
      btn_ready: 'Ready for Pickup',
      btn_take: 'Take Delivery',
      btn_pickup: 'Picked Up',
      btn_complete: 'Order Delivered',
      btn_waiting_courier: 'Waiting for courier',
      btn_waiting_kitchen: 'Waiting for kitchen',
      empty_active: 'No active orders',
      empty_active_sub: 'New orders will appear here in real time',
      empty_history: 'History is empty',
      empty_radar: 'No available orders',
      empty_radar_sub: 'Waiting for ready orders from restaurants',
      empty_search: 'No orders match your search',
      empty_menu: 'No menu items found',
      not_reg_title: 'Account Not Registered',
      not_reg_sub: 'This Telegram account is not linked to MestiDelivery partners yet.',
      not_reg_btn: 'Open Bot @MestiDelivery_Robot',
      not_reg_or_login: 'Login with username & password',
      login_title: 'Partner Login',
      login_sub: 'Use the credentials provided by administrator',
      login_btn: 'Sign In',
      lang_label: 'Interface Language',
      logout: 'Log Out',
      sound_label: 'Sound Notifications',
      confirm_cancel: 'Are you sure you want to cancel this order?',
      // Courier Info
      courier_assigned_title: 'Courier',
      courier_searching: 'Finding courier...',
      courier_waiting_title: 'Assigning Courier',
      courier_waiting_sub: 'Platform will notify couriers once ready',
      courier_call: 'Call',
      courier_status_enroute: 'Courier is en route for pickup',
      order_notes_title: 'Order Special Notes',
      // Menu Management
      menu_search_ph: 'Search by dish or ingredients...',
      menu_all_cats: 'All',
      menu_stopped_cat: 'Stop-List',
      btn_add_dish: '+ Dish',
      dish_in_stock: 'In Stock',
      dish_stopped: 'In Stop-List',
      btn_edit: 'Edit',
      modal_edit_dish_title: 'Edit Dish',
      modal_add_dish_title: 'New Dish in Menu',
      field_name: 'Dish Name',
      field_price: 'Price (₾)',
      field_category: 'Category',
      field_weight: 'Weight / volume (e.g. 250 g)',
      field_description: 'Description / ingredients',
      field_status: 'Availability Status',
      btn_save: 'Save Changes',
      btn_cancel_modal: 'Cancel',
      dish_saved_toast: 'Dish updated successfully!',
      dish_created_toast: 'Dish added to menu!',
      // Stats
      period_today: 'Today',
      period_week: '7 Days',
      period_month: 'Month',
      period_all: 'All Time',
      stats_title: 'Performance Analytics',
      kpi_revenue: 'Revenue',
      kpi_delivered: 'Delivered',
      kpi_active: 'Active',
      kpi_avg_check: 'Avg Check',
      chart_sales_dynamic: 'Sales Dynamic',
      top_dishes_title: 'Top Selling Dishes',
      payout_title: 'Financial Settlement',
      payout_rest_share: 'Kitchen Share (90%)',
      payout_platform_fee: 'Platform Fee (10%)',
      payout_ready_status: 'Ready for payout',
      // Profile Hub
      profile_hub_title: 'Control Hub',
      prep_time_title: 'Avg Preparation Time',
      auto_accept_title: 'Auto-Accept Orders',
      auto_accept_sub: 'Immediately accept incoming new orders',
      sound_test_btn: 'Test Order Chime',
      haptic_title: 'Haptic Feedback',
      haptic_sub: 'Vibrate on user actions & state changes',
      schedule_title: 'Kitchen Working Hours',
      phone_admin_title: 'Admin / Kitchen Phone',
      support_dispatcher_btn: 'Contact Dispatcher Support',
      support_report_btn: 'Report Order Issue',
      faq_title: 'Kitchen Guidelines & Standards',
      faq_q1: 'Food Packaging Standards',
      faq_a1: 'All soups and sauces must be sealed in airtight containers. Hot dishes must be packaged separately from drinks and desserts.',
      faq_q2: 'Preparation Delay (>10 min)',
      faq_a2: 'If the kitchen is overloaded or delayed, immediately notify dispatcher to inform the customer and courier.',
      faq_q3: 'Item Out of Stock',
      faq_a3: 'Switch the dish to stop-list in the Menu tab. It will instantly disappear from customer storefront.',
      faq_q4: 'Handing Order to Courier',
      faq_a4: 'Always verify the order number (e.g. #10024) with courier smartphone screen before handing over the bag.',
      btn_clear_cache: 'Clear Cache & Re-sync',
      cache_cleared_toast: 'Local cache cleared, fresh data loaded!',
      settings_saved_toast: 'Partner settings saved!',
      // Courier Keys
      tab_deliveries: 'Deliveries',
      tab_earnings: 'Earnings',
      courier_kpi_earnings: 'Earnings',
      courier_kpi_deliveries: 'Delivered',
      courier_kpi_tips: 'Tips',
      courier_kpi_avg: 'Avg Trip',
      courier_chart_title: 'Delivery Dynamics',
      courier_trips_title: 'Completed Trips',
      courier_payout_title: 'Balance & Payouts',
      courier_payout_ready: 'Ready to withdraw',
      courier_btn_withdraw: 'Request Balance Payout',
      courier_transport_title: 'Delivery Transport',
      courier_regulations_title: 'Courier Handbook & Rules',
      courier_faq_q1: 'Thermal Bag Cleanliness',
      courier_faq_a1: 'Always keep your thermal bag clean. Soups and drinks must be transported strictly vertically. Keep hot food separated from cold beverages and desserts.',
      courier_faq_q2: 'Navigation & Arrival',
      courier_faq_a2: 'Carefully verify delivery address, building, floor and intercom code. Unless marked "Do not call", call the customer 5 minutes before arrival.',
      courier_faq_q3: 'Kitchen Order Verification',
      courier_faq_a3: 'Before leaving the restaurant, verify the order ticket number on the bag against your app. Never open sealed food packages.',
      courier_faq_q4: 'Route Delays & Incidents',
      courier_faq_a4: 'In case of vehicle breakdown, severe weather or address difficulty, immediately inform the support dispatcher via the button above.'
    },
    ka: {
      brand_sub: 'პარტნიორთა სივრცე',
      online: 'ხაზზეა',
      offline: 'არაა ხაზზე',
      tab_orders: 'შეკვეთები',
      tab_menu: 'მენიუ',
      tab_stats: 'სტატისტიკა',
      tab_profile: 'პროფილი',
      sub_active: 'აქტიური',
      sub_history: 'ისტორია',
      sub_radar: 'რადარი',
      sub_my: 'ჩემი შეკვეთები',
      stat_revenue: 'შემოსავალი',
      stat_count: 'შეკვეთები',
      stat_avg: 'საშ. ჩეკი',
      order_hash: 'შეკვეთა #',
      note_prefix: 'შეკვეთის შენიშვნა:',
      total_prefix: 'გადასახდელი თანხა:',
      search_placeholder: 'ძებნა #-ით, კერძით...',
      filter_all: 'ყველა',
      filter_new: 'ახალი',
      filter_cooking: 'მზადდება',
      filter_ready: 'მზადაა',
      btn_open_details: 'დეტალების ნახვა',
      details_title: 'შეკვეთის დეტალები',
      details_back: 'უკან',
      details_copy_link: 'ბმულის კოპირება',
      details_link_copied: 'შეკვეთის ბმული დაკოპირდა!',
      details_timeline: 'შესრულების ეტაპები',
      stage_created: 'შეიქმნა',
      stage_confirmed: 'მიღებულია',
      stage_cooking: 'სამზარეულო',
      stage_ready: 'მზადაა',
      stage_delivery: 'მიწოდება',
      stage_delivered: 'ჩაბარებულია',
      client_info_title: 'კლიენტი',
      btn_call: 'დარეკვა',
      route_title: 'მიწოდების მისამართი',
      btn_open_map: 'რუკაზე გახსნა',
      ticket_title: 'შეკვეთის შემადგენლობა',
      ticket_subtotal: 'კერძების ჯამი:',
      ticket_delivery: 'მიწოდება:',
      status_new: 'ახალი',
      status_pending: 'ახალი',
      status_confirmed: 'მიღებული',
      status_accepted: 'მიღებული',
      status_preparing: 'მზადდება',
      status_ready: 'მზადაა გასაცემად',
      status_delivering: 'გზაშია',
      status_on_the_way: 'გზაშია',
      status_delivered: 'ჩაბარებული',
      status_cancelled: 'გაუქმებული',
      btn_accept: 'შეკვეთის მიღება',
      btn_cancel: 'შეკვეთის გაუქმება',
      btn_cook: 'მომზადების დაწყება',
      btn_ready: 'მზადაა გასაცემად',
      btn_take: 'შეკვეთის აღება',
      btn_pickup: 'ავიღე რესტორნიდან',
      btn_complete: 'ჩაბარებულია',
      btn_waiting_courier: 'კურიერის მოლოდინში',
      btn_waiting_kitchen: 'სამზარეულოს მოლოდინში',
      empty_active: 'აქტიური შეკვეთები არაა',
      empty_active_sub: 'ახალი შეკვეთები აქ მომენტალურად გამოჩნდება',
      empty_history: 'ისტორია ცარიელია',
      empty_radar: 'თავისუფალი შეკვეთები არაა',
      empty_radar_sub: 'დაელოდეთ შეკვეთებს რესტორნებიდან',
      empty_search: 'შეკვეთა ვერ მოიძებნა',
      empty_menu: 'მენიუს ელემენტები არ მოიძებნა',
      not_reg_title: 'ანგარიში არ არის რეგისტრირებული',
      not_reg_sub: 'ეს Telegram ანგარიში არ არის მიბმული MestiDelivery პარტნიორთა სისტემასთან.',
      not_reg_btn: 'ბოტში გადასვლა @MestiDelivery_Robot',
      not_reg_or_login: 'შესვლა ლოგინით და პაროლით',
      login_title: 'ავტორიზაცია',
      login_sub: 'გამოიყენეთ ადმინისტრატორის მიერ მოწოდებული მონაცემები',
      login_btn: 'შესვლა',
      lang_label: 'ინტერფეისის ენა',
      logout: 'გასვლა',
      sound_label: 'ხმოვანი შეტყობინებები',
      confirm_cancel: 'დარწმუნებული ხართ, რომ გსურთ შეკვეთის გაუქმება?',
      // Courier Info
      courier_assigned_title: 'კურიერი',
      courier_searching: 'კურიერის ძიება...',
      courier_waiting_title: 'კურიერის მოძიება',
      courier_waiting_sub: 'პლატფორმა შეატყობინებს კურიერებს',
      courier_call: 'დარეკვა',
      courier_status_enroute: 'კურიერი მოდის შეკვეთისთვის',
      order_notes_title: 'შეკვეთის შენიშვნა',
      // Menu Management
      menu_search_ph: 'ძებნა კერძებით ან შემადგენლობით...',
      menu_all_cats: 'ყველა',
      menu_stopped_cat: 'სტოპ-ლისტი',
      btn_add_dish: '+ კერძი',
      dish_in_stock: 'მარაგშია',
      dish_stopped: 'სტოპ-ლისტში',
      btn_edit: 'შეცვლა',
      modal_edit_dish_title: 'კერძის რედაქტირება',
      modal_add_dish_title: 'ახალი კერძი მენიუში',
      field_name: 'კერძის სახელი',
      field_price: 'ფასი (₾)',
      field_category: 'კატეგორია',
      field_weight: 'წონა / მოცულობა (მაგ. 250 გ)',
      field_description: 'აღწერა / შემადგენლობა',
      field_status: 'ხელმისაწვდომობის სტატუსი',
      btn_save: 'შენახვა',
      btn_cancel_modal: 'გაუქმება',
      dish_saved_toast: 'კერძი განახლდა!',
      dish_created_toast: 'კერძი დაემატა მენიუში!',
      // Stats
      period_today: 'დღეს',
      period_week: '7 დღე',
      period_month: 'თვე',
      period_all: 'სულ',
      stats_title: 'რესტორნის ანალიტიკა',
      kpi_revenue: 'შემოსავალი',
      kpi_delivered: 'ჩაბარებული',
      kpi_active: 'აქტიური',
      kpi_avg_check: 'საშ. ჩეკი',
      chart_sales_dynamic: 'გაყიდვების დინამიკა',
      top_dishes_title: 'ტოპ კერძები',
      payout_title: 'ფინანსური ანგარიშსწორება',
      payout_rest_share: 'სამზარეულოს წილი (90%)',
      payout_platform_fee: 'პლატფორმის საკომისიო (10%)',
      payout_ready_status: 'მზადაა ანგარიშსწორებისთვის',
      // Profile Hub
      profile_hub_title: 'მართვის პანელი',
      prep_time_title: 'მომზადების საშუალო დრო',
      auto_accept_title: 'შეკვეთების ავტო-მიღება',
      auto_accept_sub: 'ახალი შეკვეთების მომენტალური მიღება',
      sound_test_btn: 'ხმის შემოწმება',
      haptic_title: 'ვიბრაცია',
      haptic_sub: 'ვიბრაცია მოქმედებებზე',
      schedule_title: 'სამუშაო გრაფიკი',
      phone_admin_title: 'ადმინისტრატორის ნომერი',
      support_dispatcher_btn: 'დისპეტჩერთან დაკავშირება',
      support_report_btn: 'პრობლემის შეტყობინება',
      faq_title: 'ინსტრუქცია და რეგლამენტი',
      faq_q1: 'შეფუთვის სტანდარტები',
      faq_a1: 'წვნიანები და სოუსები უნდა შეიფუთოს ჰერმეტულად. ცხელი კერძები ცივი სასმელებისგან განცალკევებით უნდა მოთავსდეს.',
      faq_q2: 'მომზადების დაგვიანება (>10 წთ)',
      faq_a2: 'სამზარეულოს დატვირთვისას დაუყოვნებლივ აცნობეთ დისპეტჩერს კლიენტის გასაფრთხილებლად.',
      faq_q3: 'პროდუქტი ამოიწურა',
      faq_a3: 'გადაიტანეთ კერძი სტოპ-ლისტში მენიუს განყოფილებიდან.',
      faq_q4: 'კურიერისთვის გადაცემა',
      faq_a4: 'ყოველთვის გადაამოწმეთ შეკვეთის ნომერი (#10024) კურიერის ტელეფონის ეკრანზე.',
      btn_clear_cache: 'ქეშის გასუფთავება და სინქრონიზაცია',
      cache_cleared_toast: 'ქეში გასუფთავდა, მონაცემები განახლდა!',
      settings_saved_toast: 'პარამეტრები შენახულია!',
      // Courier Keys
      tab_deliveries: 'მიწოდებები',
      tab_earnings: 'შემოსავალი',
      courier_kpi_earnings: 'გამომუშავებული',
      courier_kpi_deliveries: 'ჩაბარებული',
      courier_kpi_tips: 'თიფსი',
      courier_kpi_avg: 'საშ. რეისი',
      courier_chart_title: 'მიწოდებების დინამიკა',
      courier_trips_title: 'შესრულებული რეისები',
      courier_payout_title: 'ბალანსი და გატანა',
      courier_payout_ready: 'მზადაა გასატანად',
      courier_btn_withdraw: 'თანხის გატანის მოთხოვნა',
      courier_transport_title: 'კურიერის ტრანსპორტი',
      courier_regulations_title: 'კურიერის რეგლამენტი და წესები',
      courier_faq_q1: 'თერმოჩანთის სისუფთავე',
      courier_faq_a1: 'ყოველთვის შეინარჩუნეთ თერმოჩანთა სუფთად. წვნიანები და სასმელები გადაიტანეთ მკაცრად ვერტიკალურად.',
      courier_faq_q2: 'ნავიგაცია და მისვლა',
      courier_faq_a2: 'გადაამოწმეთ მისამართი, სადარბაზო და სართული. დარეკეთ კლიენტთან მისვლამდე 5 წუთით ადრე.',
      courier_faq_q3: 'შეკვეთის შემოწმება',
      courier_faq_a3: 'რესტორნიდან გატანისას შეადარეთ ჩეკის ნომერი აპლიკაციის ნომერს. არ გახსნათ შეფუთვები.',
      courier_faq_q4: 'შეფერხებები და ფორს-მაჟორი',
      courier_faq_a4: 'დაბრკოლების ან დაგვიანების შემთხვევაში დაუყოვნებლივ დაუკავშირდით დისპეტჩერს.'
    }
  };

  function getTelegramLanguage() {
    const tgUser = extractTelegramUser();
    const raw = tgUser?.language_code || getTG()?.initDataUnsafe?.user?.language_code;
    if (!raw) return null;
    const code = String(raw).toLowerCase().trim();
    if (code.startsWith('ka') || code.startsWith('ge')) return 'ka';
    if (code.startsWith('en')) return 'en';
    if (code.startsWith('ru')) return 'ru';
    return null;
  }

  function resolveLanguage() {
    const manual = safeStorage.get('partner_lang_manual');
    if (manual && I18N[manual]) return manual;

    const tgLang = getTelegramLanguage();
    if (tgLang && I18N[tgLang]) return tgLang;

    const saved = safeStorage.get('partner_lang');
    if (saved && I18N[saved]) return saved;

    const nav = (navigator.language || '').slice(0, 2).toLowerCase();
    if (nav === 'ka' || nav === 'ge') return 'ka';
    if (nav === 'en') return 'en';
    return 'ru';
  }

  let currentLang = resolveLanguage();

  function t(key) {
    return I18N[currentLang]?.[key] || I18N.ru[key] || key;
  }

  // 7. Application State
  function isKitchenRole() {
    // 1. Authenticated user takes absolute precedence over everything
    if (state && state.user) {
      const r = (state.user.role || '').toLowerCase();
      const u = (state.user.username || '').toLowerCase();
      const rid = state.user.restaurant_id;

      // If user has restaurant_id or username matches restaurant patterns -> STRICTLY Kitchen
      if (r === 'restaurant_admin' || r === 'restaurant' || Boolean(rid) || u.startsWith('test_rest') || u.startsWith('admin_') || u.includes('rest')) {
        return true;
      }
      // Only strictly courier with no restaurant_id -> Courier
      if (r === 'courier' || Boolean(state.user.courier_id) || u.startsWith('courier_') || u === 'test_courier') {
        return false;
      }
    }

    // 2. Query parameter only acts as a fallback when no authenticated user exists
    try {
      const p = new URLSearchParams(window.location.search);
      const r = p.get('role');
      if (r === 'restaurant' || r === 'kitchen') return true;
      if (r === 'courier') return false;
    } catch (e) {}

    return true;
  }

  function getEffectiveRole() {
    return isKitchenRole() ? 'restaurant' : 'courier';
  }

  const state = {
    courierTransport: safeStorage.get('courier_transport', 'bike'),
    user: (() => {
      try {
        const raw = safeStorage.get('mesti_partner_user');
        if (!raw) return null;
        const u = JSON.parse(raw);
        if (u) {
          const savedPhoto = safeStorage.get('mesti_tg_photo');
          if (savedPhoto && !u.photo_url) {
            u.photo_url = savedPhoto;
          }
          const uname = (u.username || '').toLowerCase();
          // Auto-heal: if username is test_rest or restaurant account, guarantee restaurant_admin role
          if (uname.includes('rest') || uname.startsWith('admin_') || u.restaurant_id) {
            u.role = 'restaurant_admin';
            if (!u.restaurant_id) u.restaurant_id = 'test_rest_01';
            safeStorage.set('mesti_partner_user', JSON.stringify(u));
          }
        }
        return u;
      } catch (e) { return null; }
    })(),
    orders: (() => {
      try {
        const raw = safeStorage.get('mesti_partner_orders');
        return raw ? JSON.parse(raw) : [];
      } catch (e) { return []; }
    })(),
    dishes: (() => {
      try {
        const raw = safeStorage.get('mesti_partner_menu');
        return raw ? JSON.parse(raw) : [];
      } catch (e) { return []; }
    })(),
    isOnline: safeStorage.get('partner_online', 'true') === 'true',
    currentTab: 'orders', // orders, menu, stats, profile
    subTab: 'active',
    statusFilter: 'all',
    searchQuery: '',
    selectedOrderId: null,
    soundEnabled: safeStorage.get('partner_sound', 'true') === 'true',
    hapticEnabled: safeStorage.get('partner_haptic', 'true') === 'true',
    autoAccept: safeStorage.get('partner_auto_accept', 'false') === 'true',
    prepTime: safeStorage.get('partner_prep_time', '25'),
    kitchenSchedule: safeStorage.get('partner_schedule', '10:00 - 23:00'),
    kitchenPhone: safeStorage.get('partner_kitchen_phone', '+995 595 00 00 00'),
    isSyncing: false,
    showManualLogin: false,
    notRegisteredUser: null,
    // Menu & Stats
    menuCategories: [],
    menuActiveCat: 'all',
    menuSearchQuery: '',
    editingDish: null,
    isAddingDish: false,
    statsPeriod: 'week',
    statsData: null
  };

  // 8. Backend API Client
  const api = {
    getHeaders() {
      const h = { 'Content-Type': 'application/json' };
      const token = state.user?.token || safeStorage.get('admin_token') || safeStorage.get('delivery_jwt_token');
      if (token) h['Authorization'] = `Bearer ${token}`;
      const tg = getTG();
      if (tg?.initData) h['X-Telegram-Init-Data'] = tg.initData;
      return h;
    },

    async autoTelegramAuth(tgUser) {
      if (!tgUser?.id) return null;
      try {
        const tg = getTG();
        const photoUrl = tgUser.photo_url || safeStorage.get('mesti_tg_photo') || '';
        const res = await fetch('/api/bot/v1/auth/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            telegram_id: tgUser.id,
            username: tgUser.username || '',
            first_name: tgUser.first_name || '',
            photo_url: photoUrl,
            language_code: tgUser.language_code || '',
            init_data: tg?.initData || ''
          })
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.ok && data.token) {
            if (data.user?.language && I18N[data.user.language]) {
              currentLang = data.user.language;
              safeStorage.set('partner_lang', currentLang);
            }
            const returnedPhoto = data.user?.photo_url || photoUrl;
            if (returnedPhoto) {
              safeStorage.set('mesti_tg_photo', returnedPhoto);
            }
            return {
              ok: true,
              user: {
                id: data.user?.id || tgUser.id,
                username: data.user?.username || tgUser.username,
                name: data.user?.restaurant_name || data.user?.name || tgUser.first_name,
                role: data.user?.role || 'restaurant_admin',
                restaurant_id: data.user?.restaurant_id || 'test_rest_01',
                courier_id: data.user?.courier_id || 0,
                photo_url: returnedPhoto,
                token: data.token
              }
            };
          }
          if (data && data.registered === false) {
            return { not_registered: true, bot_username: data.bot_username || 'MestiDelivery_Robot' };
          }
        }
      } catch (e) {
        console.warn('autoTelegramAuth note:', e);
      }
      return null;
    },

    async loginWithCredentials(username, password) {
      let res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (!res.ok) {
        res = await fetch('/api/admin/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        if (!res.ok) throw new Error('Неверный логин или пароль');
      }
      const data = await res.json();
      const uObj = (data && typeof data.user === 'object' && data.user) ? data.user : data;

      const rawRole = (uObj.role || data.role || '').toLowerCase();
      const uname = (uObj.username || data.username || username || '').toLowerCase();
      const restId = uObj.restaurant_id || data.restaurant_id || (uname.includes('rest') ? 'test_rest_01' : '');

      let determinedRole = 'restaurant_admin';
      if (rawRole === 'courier' || uname.startsWith('courier_') || uname === 'test_courier') {
        determinedRole = 'courier';
      } else if (rawRole === 'restaurant_admin' || rawRole === 'restaurant' || restId) {
        determinedRole = 'restaurant_admin';
      } else if (uname.includes('rest') || uname.startsWith('admin_')) {
        determinedRole = 'restaurant_admin';
      }

      return {
        id: uObj.id || data.user_id || data.id || 24,
        username: uObj.username || data.username || username,
        name: uObj.restaurant_name || data.restaurant_name || uObj.name || data.name || username,
        role: determinedRole,
        restaurant_id: restId || (determinedRole === 'restaurant_admin' ? 'test_rest_01' : ''),
        courier_id: uObj.courier_id || data.courier_id || 0,
        token: data.token || data.access_token || ''
      };
    },

    async fetchOrders() {
      if (!state.user) return [];
      const effectiveRole = getEffectiveRole();
      let url = `/api/bot/v1/partner/orders?limit=60`;
      if (effectiveRole === 'restaurant') {
        const restId = state.user.restaurant_id || 'test_rest_01';
        url += `&restaurant_id=${encodeURIComponent(restId)}`;
      } else {
        const courId = state.user.courier_id || 14;
        url += `&courier_id=${encodeURIComponent(courId)}`;
      }

      try {
        const res = await fetch(url, { headers: this.getHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.orders)) return data.orders;
        }
      } catch (e) {}
      return state.orders;
    },

    async updateOrderStatus(orderId, newStatus) {
      try {
        const body = { status: newStatus };
        if (state.user?.courier_id) body.courier_id = state.user.courier_id;
        const photo = state.user?.photo_url || safeStorage.get('mesti_tg_photo');
        if (photo) body.courier_photo = photo;

        const res = await fetch(`/api/bot/v1/partner/order/${orderId}/status`, {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify(body)
        });
        return res.ok;
      } catch (e) {
        return false;
      }
    },

    async fetchMenu() {
      const restId = state.user?.restaurant_id || 'test_rest_01';
      try {
        const res = await fetch(`/api/bot/v1/partner/menu?restaurant_id=${encodeURIComponent(restId)}`, {
          headers: this.getHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.dishes)) {
            state.dishes = data.dishes;
            state.menuCategories = data.categories || [];
            safeStorage.set('mesti_partner_menu', JSON.stringify(data.dishes));
            return data;
          }
        }
      } catch (e) {}
      return { dishes: state.dishes, categories: [] };
    },

    async toggleDishAvailability(dishId, isAvailable) {
      try {
        const res = await fetch('/api/bot/v1/partner/menu/toggle', {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify({ dish_id: dishId, is_available: isAvailable })
        });
        return res.ok;
      } catch (e) {
        return false;
      }
    },

    async updateDish(dishData) {
      try {
        const res = await fetch('/api/bot/v1/partner/menu/update', {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify(dishData)
        });
        return res.ok;
      } catch (e) {
        return false;
      }
    },

    async createDish(dishData) {
      try {
        const res = await fetch('/api/bot/v1/partner/menu/create', {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify(dishData)
        });
        return res.ok;
      } catch (e) {
        return false;
      }
    },

    async fetchStats(period = 'week') {
      const restId = state.user?.restaurant_id || '';
      const courId = state.user?.courier_id || 0;
      let url = `/api/bot/v1/partner/stats?period=${encodeURIComponent(period)}`;
      if (restId) url += `&restaurant_id=${encodeURIComponent(restId)}`;
      else if (courId > 0) url += `&courier_id=${encodeURIComponent(courId)}`;

      try {
        const res = await fetch(url, { headers: this.getHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data && (data.stats || data.revenue !== undefined)) {
            const resultStats = data.stats || data;
            state.statsData = resultStats;
            return resultStats;
          }
        }
      } catch (e) {}
      return null;
    }
  };

  function formatElapsed(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      const now = new Date();
      const sec = Math.floor((now - d) / 1000);
      if (sec < 60) return currentLang === 'ka' ? 'ახლახან' : currentLang === 'en' ? 'just now' : 'только что';
      const min = Math.floor(sec / 60);
      if (min < 60) return currentLang === 'ka' ? `${min} წთ უკან` : currentLang === 'en' ? `${min}m ago` : `${min} мин назад`;
      const hr = Math.floor(min / 60);
      return currentLang === 'ka' ? `${hr} სთ უკან` : currentLang === 'en' ? `${hr}h ago` : `${hr} ч назад`;
    } catch (e) {
      return '';
    }
  }

  function getTitle(raw) {
    if (!raw) return '';
    if (typeof raw === 'object') {
      return raw[currentLang] || raw.ru || raw.en || raw.ka || '';
    }
    if (typeof raw === 'string' && raw.trim().startsWith('{')) {
      try {
        const obj = JSON.parse(raw);
        return obj[currentLang] || obj.ru || obj.en || obj.ka || raw;
      } catch (e) {
        return raw;
      }
    }
    return String(raw);
  }

  function showToast(text) {
    const existing = document.getElementById('floating-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'floating-toast';
    toast.className = 'toast-box';
    toast.innerHTML = `${iconSvg("sparkle", "", 16)}<span>${text}</span>`;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translate(-50%, 10px)';
      setTimeout(() => toast.remove(), 250);
    }, 2400);
  }

  // 9. Deep-Link & URL Routing
  function openOrderDetails(orderId) {
    const id = Number(orderId);
    if (!id) return;
    haptic('light');
    state.selectedOrderId = id;

    try {
      const u = new URL(window.location.href);
      u.searchParams.set('order_id', id);
      window.history.pushState({ orderId: id }, '', u.toString());
    } catch (e) {}

    const tg = getTG();
    if (tg?.BackButton) {
      tg.BackButton.show();
      tg.BackButton.onClick(closeOrderDetails);
    }

    renderApp();
    window.scrollTo(0, 0);
  }

  function closeOrderDetails() {
    haptic('light');
    state.selectedOrderId = null;

    try {
      const u = new URL(window.location.href);
      u.searchParams.delete('order_id');
      window.history.pushState({}, '', u.pathname + (u.search ? u.search : ''));
    } catch (e) {}

    const tg = getTG();
    if (tg?.BackButton) {
      tg.BackButton.hide();
    }

    renderApp();
  }

  window.addEventListener('popstate', (e) => {
    const params = new URLSearchParams(window.location.search);
    const ordId = params.get('order_id');
    if (ordId) {
      state.selectedOrderId = Number(ordId);
      const tg = getTG();
      if (tg?.BackButton) {
        tg.BackButton.show();
        tg.BackButton.onClick(closeOrderDetails);
      }
    } else {
      state.selectedOrderId = null;
      const tg = getTG();
      if (tg?.BackButton) {
        tg.BackButton.hide();
      }
    }
    renderApp();
  });

  function copyOrderLink(orderId) {
    const url = `https://partners.mestidelivery.com/?order_id=${orderId}`;
    haptic('success');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(() => {
        showToast(t('details_link_copied'));
      }).catch(() => {
        prompt('Ссылка на заказ:', url);
      });
    } else {
      prompt('Ссылка на заказ:', url);
    }
  }

  // 10. UI Rendering
  function renderApp() {
    const root = document.getElementById('root');
    if (!root) return;

    if (!state.user) {
      if (state.notRegisteredUser && !state.showManualLogin) {
        renderNotRegistered(root);
      } else {
        renderLogin(root);
      }
      return;
    }

    if (state.selectedOrderId) {
      renderOrderDetailsView(root, state.selectedOrderId);
      return;
    }

    const isKitchen = isKitchenRole();
    if (!isKitchen && state.currentTab === 'menu') {
      state.currentTab = 'orders';
    }

    let revenue = 0;
    let completedCount = 0;
    let activeCount = 0;

    state.orders.forEach(o => {
      const isDone = o.status === 'delivered';
      const isCancelled = o.status === 'cancelled';
      if (!isDone && !isCancelled) activeCount++;
      if (isDone) {
        revenue += Number(o.total || 0);
        completedCount++;
      }
    });

    const avg = completedCount > 0 ? (revenue / completedCount).toFixed(1) : '0';
    const courierEarnings = (completedCount * 8.0).toFixed(1);

        let partnerTitle = isKitchen
      ? (state.user?.restaurant_name || state.user?.name || 'Кухня')
      : (state.user?.name || state.user?.username || 'Курьер');

    if (partnerTitle === 'test_rest' || partnerTitle === 'test_rest_01') {
      partnerTitle = 'Тестовый Ресторан';
    }

    const partnerRole = isKitchen ? 'Кухня' : 'Курьер';
    const isModalOpen = Boolean(state.editingDish || state.isAddingDish);
    if (isModalOpen) {
      document.body.classList.add('modal-open');
    } else {
      document.body.classList.remove('modal-open');
    }

    root.innerHTML = `
      <div class="app-wrapper">
        <!-- Top Header (Cyber-Luxe Obsidian Header) -->
        <header class="top-header">
          <div class="header-brand-wrap">
            ${!isKitchen ? `
              <div class="header-identity-box courier-mode">
                ${(state.user?.photo_url || safeStorage.get('mesti_tg_photo')) ? `
                  <img src="${state.user?.photo_url || safeStorage.get('mesti_tg_photo')}" class="header-identity-img" alt="${partnerTitle}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                  <span class="header-identity-initials" style="display: none;">${partnerTitle.charAt(0).toUpperCase()}</span>
                ` : `
                  <span class="header-identity-initials">${partnerTitle.charAt(0).toUpperCase()}</span>
                `}
              </div>
              <div class="header-brand-meta">
                <span class="header-brand-title">${partnerTitle}</span>
                <span class="header-brand-subtitle">Курьер • Доставка</span>
              </div>
            ` : `
              <div class="header-identity-box kitchen-mode">
                <img src="/Assets/general-green.png" alt="Mesti" class="header-identity-logo" />
              </div>
              <div class="header-brand-meta">
                <span class="header-brand-title">${partnerTitle}</span>
                <span class="header-brand-subtitle">Кухня • Терминал</span>
              </div>
            `}
          </div>
          <div class="header-actions">
            <button class="status-capsule-btn ${state.isOnline ? 'is-online' : 'is-offline'}" id="btn-shift">
              <span class="status-beacon-dot"></span>
              <span class="status-text">${state.isOnline ? (isKitchen ? 'Открыто' : 'На смене') : (isKitchen ? 'Закрыто' : 'Не на смене')}</span>
            </button>
          </div>
        </header>

        ${state.currentTab === 'orders' ? `
          <!-- Executive Metric Strip (Minimalist Replacement for Clunky Boxes) -->
          <div class="metrics-strip">
            <div class="metric-col">
              <span class="metric-col-label">${isKitchen ? t('stat_revenue') : t('courier_kpi_earnings')}</span>
              <span class="metric-col-val highlight">${isKitchen ? revenue.toFixed(1) + ' ₾' : courierEarnings + ' ₾'}</span>
            </div>
            <div class="metric-col">
              <span class="metric-col-label">${isKitchen ? t('stat_count') : t('courier_kpi_deliveries')}</span>
              <span class="metric-col-val">${completedCount}</span>
            </div>
            <div class="metric-col">
              <span class="metric-col-label">${isKitchen ? t('stat_avg') : t('courier_kpi_tips')}</span>
              <span class="metric-col-val">${isKitchen ? avg + ' ₾' : '0.0 ₾'}</span>
            </div>
          </div>
        ` : ''}

        <!-- Body -->
        ${renderBody(isKitchen, activeCount)}

        ${!isModalOpen ? `
        <!-- Bottom Fixed Navigation -->
        <nav class="bottom-nav">
          <button class="tab-btn ${state.currentTab === 'orders' ? 'is-active' : ''}" data-nav="orders">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <path d="M12 11h4"/>
              <path d="M12 16h4"/>
              <path d="M8 11h.01"/>
              <path d="M8 16h.01"/>
            </svg>
            <span class="tab-label">${isKitchen ? t('tab_orders') : t('tab_deliveries')}</span>
            ${activeCount > 0 ? `<span class="tab-bubble">${activeCount}</span>` : ''}
          </button>

          ${isKitchen ? `
            <button class="tab-btn ${state.currentTab === 'menu' ? 'is-active' : ''}" data-nav="menu">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/>
                <path d="M7 2v20"/>
                <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>
              </svg>
              <span class="tab-label">${t('tab_menu')}</span>
            </button>
          ` : ''}

          <button class="tab-btn ${state.currentTab === 'stats' ? 'is-active' : ''}" data-nav="stats">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" x2="18" y1="20" y2="10"/>
              <line x1="12" x2="12" y1="20" y2="4"/>
              <line x1="6" x2="6" y1="20" y2="14"/>
            </svg>
            <span class="tab-label">${isKitchen ? t('tab_stats') : t('tab_earnings')}</span>
          </button>

          <button class="tab-btn ${state.currentTab === 'profile' ? 'is-active' : ''}" data-nav="profile">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <span class="tab-label">${t('tab_profile')}</span>
          </button>
        </nav>
        ` : ''}
      </div>

      <!-- Modals -->
      ${state.editingDish ? renderEditDishModal(state.editingDish) : ''}
      ${state.isAddingDish ? renderAddDishModal() : ''}
    `;

    bindEvents();
  }

  function renderBody(isKitchen, activeCount) {
    if (isKitchen && state.currentTab === 'menu') return renderMenuTab();
    if (state.currentTab === 'stats') {
      return isKitchen ? renderKitchenStatsTab() : renderCourierStatsTab();
    }
    if (state.currentTab === 'profile') {
      return isKitchen ? renderKitchenProfileTab() : renderCourierProfileTab();
    }

    const isRadar = !isKitchen && state.subTab === 'radar';
    const isHistory = state.subTab === 'history';

    let list = [];
    if (isKitchen) {
      if (isHistory) {
        list = state.orders.filter(o => o.status === 'delivered' || o.status === 'cancelled');
      } else {
        list = state.orders.filter(o => o.status !== 'delivered' && o.status !== 'cancelled');
      }
    } else {
      if (isRadar) {
        list = state.orders.filter(o => !o.courier_id && (o.status === 'confirmed' || o.status === 'accepted' || o.status === 'preparing' || o.status === 'ready'));
      } else if (isHistory) {
        list = state.orders.filter(o => o.courier_id === state.user?.courier_id && (o.status === 'delivered' || o.status === 'cancelled'));
      } else {
        list = state.orders.filter(o => o.courier_id === state.user?.courier_id && o.status !== 'delivered' && o.status !== 'cancelled');
      }
    }

    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      list = list.filter(o => {
        const idMatch = String(o.id || o.order_id).includes(q);
        const commentMatch = (o.comment || '').toLowerCase().includes(q);
        const restMatch = (o.restaurant_name || '').toLowerCase().includes(q);
        let itemMatch = false;
        try {
          const items = Array.isArray(o.items) ? o.items : JSON.parse(o.items_json || '[]');
          itemMatch = items.some(it => (it.name || it.title || '').toLowerCase().includes(q));
        } catch(e) {}
        return idMatch || commentMatch || restMatch || itemMatch;
      });
    }

    if (state.statusFilter !== 'all' && !isHistory && !isRadar) {
      if (state.statusFilter === 'new') {
        list = list.filter(o => o.status === 'new' || o.status === 'pending');
      } else if (state.statusFilter === 'cooking') {
        list = list.filter(o => o.status === 'confirmed' || o.status === 'accepted' || o.status === 'preparing');
      } else if (state.statusFilter === 'ready') {
        list = list.filter(o => o.status === 'ready');
      }
    }

    return `
      <!-- Minimal Search Input -->
      <div class="search-wrap">
        <div class="search-box">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--brand)">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.3-4.3"></path>
          </svg>
          <input type="text" id="inp-search" class="search-input" placeholder="${t('search_placeholder')}" value="${state.searchQuery}" />
          ${state.searchQuery ? `<span class="search-clear" id="btn-clear-search">${iconSvg("cross", "", 14)}</span>` : ''}
        </div>
      </div>

      <!-- Single Elegant Pill Chips Row (Replaces Clunky Nested Tab Rows) -->
      <div class="chips-scroll-row">
        ${isKitchen ? `
          <button class="filter-pill-btn ${state.subTab === 'active' && state.statusFilter === 'all' ? 'is-active' : ''}" data-nav-action="kitchen-all">
            <span>${t('filter_all')}</span>
            ${activeCount > 0 ? `<span class="pill-counter">${activeCount}</span>` : ''}
          </button>
          <button class="filter-pill-btn ${state.subTab === 'active' && state.statusFilter === 'new' ? 'is-active' : ''}" data-nav-action="kitchen-new">
            <span>${t('filter_new')}</span>
          </button>
          <button class="filter-pill-btn ${state.subTab === 'active' && state.statusFilter === 'cooking' ? 'is-active' : ''}" data-nav-action="kitchen-cooking">
            <span>${t('filter_cooking')}</span>
          </button>
          <button class="filter-pill-btn ${state.subTab === 'active' && state.statusFilter === 'ready' ? 'is-active' : ''}" data-nav-action="kitchen-ready">
            <span>${t('filter_ready')}</span>
          </button>
          <button class="filter-pill-btn ${state.subTab === 'history' ? 'is-active' : ''}" data-nav-action="history">
            <span>${t('sub_history')}</span>
          </button>
        ` : `
          <button class="filter-pill-btn ${state.subTab === 'radar' ? 'is-active' : ''}" data-nav-action="radar">
            <span>${t('sub_radar')}</span>
          </button>
          <button class="filter-pill-btn ${state.subTab === 'active' ? 'is-active' : ''}" data-nav-action="courier-my">
            <span>${t('sub_my')}</span>
            ${activeCount > 0 ? `<span class="pill-counter">${activeCount}</span>` : ''}
          </button>
          <button class="filter-pill-btn ${state.subTab === 'history' ? 'is-active' : ''}" data-nav-action="history">
            <span>${t('sub_history')}</span>
          </button>
        `}
      </div>

      <div class="feed-container">
        ${list.length === 0 ? `
          <div class="empty-wrap">
            <div class="empty-icon-wrap">
              ${isRadar ? iconSvg("radar", "", 28) : iconSvg("package", "", 28)}
            </div>
            <div class="empty-headline">${state.searchQuery ? t('empty_search') : isHistory ? t('empty_history') : isRadar ? t('empty_radar') : t('empty_active')}</div>
            <div class="empty-detail">${isHistory ? '' : isRadar ? t('empty_radar_sub') : t('empty_active_sub')}</div>
          </div>
        ` : list.map(o => renderCard(o, isKitchen)).join('')}
      </div>
    `;
  }

  function renderCard(order, isKitchen) {
    const id = Number(order.id || order.order_id);
    const status = (order.status || 'new').toLowerCase();
    const isNew = status === 'new' || status === 'pending';
    const total = Number(order.total || 0).toFixed(2);
    const elapsed = formatElapsed(order.created_at);

    let items = [];
    if (Array.isArray(order.items)) items = order.items;
    else if (typeof order.items_json === 'string') {
      try { items = JSON.parse(order.items_json); } catch (e) {}
    }

    const statusLabel = t(`status_${status}`) || status;
    const hasCourier = Boolean(order.courier_name || order.courier_phone || (order.courier_id && Number(order.courier_id) > 0));

    return `
      <div class="card ${isNew ? 'is-new-order' : ''}" data-card-id="${id}">
        <div class="card-header" data-open-id="${id}" style="cursor: pointer;">
          <div class="card-title-wrap">
            <span class="order-id">${t('order_hash')}${id}</span>
            ${elapsed ? `<span class="order-elapsed">• ${elapsed}</span>` : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="status-tag status-${status}">
              <span class="status-tag-dot"></span>
              <span>${statusLabel}</span>
            </span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--text-muted);">
              <path d="m9 18 6-6-6-6"/>
            </svg>
          </div>
        </div>

        ${isKitchen ? `
          ${items.length > 0 ? `
            <div class="items-table" data-open-id="${id}" style="cursor: pointer;">
              ${items.slice(0, 3).map(it => {
                const qty = Number(it.quantity || 1);
                return `
                <div class="item-line">
                  <div class="item-left">
                    <span class="item-qty-badge ${qty > 1 ? 'is-multi' : ''}">${qty}×</span>
                    <span class="item-title">${getTitle(it.name || it.title)}</span>
                  </div>
                  <span class="item-cost">${((Number(it.price || 0)) * qty).toFixed(1)} ₾</span>
                </div>
              `;}).join('')}
              ${items.length > 3 ? `<div class="items-more-link" data-open-id="${id}">+ ещё ${items.length - 3} поз.</div>` : ''}
            </div>
          ` : ''}

          ${order.comment ? `
            <div class="note-callout">
              <strong>${t('note_prefix')}</strong> ${order.comment}
            </div>
          ` : ''}

          <div class="card-summary">
            <span class="summary-label">${t('total_prefix')}</span>
            <span class="total-amount">${total} ₾</span>
          </div>
        ` : `
          <!-- Courier Vertical Route Stepper (Direct from Official Banner 5a) -->
          <div class="courier-route-block">
            <div class="route-node">
              <div class="route-marker-circle"></div>
              <div class="route-node-content">
                <span class="route-node-tag">PICK UP</span>
                <span class="route-node-val">${order.restaurant_name || 'Ресторан MestiDelivery'}</span>
              </div>
            </div>
            <div class="route-dash-connector"></div>
            <div class="route-node">
              <div class="route-marker-pin">${iconSvg("pin", "", 13)}</div>
              <div class="route-node-content">
                <span class="route-node-tag">DROP OFF</span>
                <span class="route-node-val">${order.address || 'Адрес клиента'}</span>
              </div>
            </div>
          </div>

          <div class="courier-payout-row">
            <span class="payout-tag">ВЫПЛАТА КУРЬЕРУ</span>
            <span class="payout-val">8.00 ₾</span>
          </div>

          ${order.comment ? `
            <div class="note-callout">
              <strong>${t('note_prefix')}</strong> ${order.comment}
            </div>
          ` : ''}
        `}

        ${renderActionBtn(id, status, isKitchen)}
      </div>
    `;
  }

  function renderActionBtn(orderId, status, isKitchen) {
    if (isKitchen) {
      if (status === 'new' || status === 'pending') {
        return `
          <button class="btn-primary-action" data-btn-action="advance" data-id="${orderId}" data-target="confirmed">
            ${iconSvg('check', '', 16)}
            <span>${t('btn_accept')}</span>
          </button>
          <button class="btn-secondary-danger" data-btn-action="cancel" data-id="${orderId}">
            ${iconSvg('cross', '', 14)}
            <span>${t('btn_cancel')}</span>
          </button>
        `;
      }
      if (status === 'confirmed' || status === 'accepted') {
        return `
          <button class="btn-primary-action state-cook" data-btn-action="advance" data-id="${orderId}" data-target="preparing">
            ${iconSvg('kitchen', '', 16)}
            <span>${t('btn_cook')}</span>
          </button>
        `;
      }
      if (status === 'preparing') {
        return `
          <button class="btn-primary-action state-ready" data-btn-action="advance" data-id="${orderId}" data-target="ready">
            ${iconSvg('check', '', 16)}
            <span>${t('btn_ready')}</span>
          </button>
        `;
      }
      if (status === 'ready') {
        return `
          <div class="state-badge-waiting">
            ${iconSvg('scooter', '', 16)} <span>${t('btn_waiting_courier')}</span>
          </div>
        `;
      }
      return '';
    } else {
      if (!status || status === 'confirmed' || status === 'accepted') {
        return `
          <button class="btn-primary-action" data-btn-action="take" data-id="${orderId}">
            ${iconSvg('scooter', '', 16)}
            <span>${t('btn_take')}</span>
          </button>
        `;
      }
      if (status === 'preparing') {
        return `
          <div class="state-badge-waiting">
            ${iconSvg('kitchen', '', 16)} <span>${t('btn_waiting_kitchen')}</span>
          </div>
        `;
      }
      if (status === 'ready') {
        return `
          <button class="btn-primary-action state-cook" data-btn-action="advance" data-id="${orderId}" data-target="delivering">
            ${iconSvg('scooter', '', 16)}
            <span>${t('btn_pickup')}</span>
          </button>
        `;
      }
      if (status === 'delivering' || status === 'on_the_way') {
        return `
          <button class="btn-primary-action state-ready" data-btn-action="advance" data-id="${orderId}" data-target="delivered">
            ${iconSvg('check', '', 16)}
            <span>${t('btn_complete')}</span>
          </button>
        `;
      }
      return '';
    }
  }

    // 11. Dedicated Order Details View (Minimalist Luxury Terminal v8.1)
  function renderOrderDetailsView(root, orderId) {
    const order = state.orders.find(o => Number(o.id || o.order_id) === Number(orderId));
    if (!order) {
      root.innerHTML = `
        <div class="details-view">
          <header class="details-header">
            <button class="details-back-icon-btn" id="btn-back-feed" aria-label="${t('details_back')}" title="${t('details_back')}">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m15 18-6-6 6-6"/>
              </svg>
            </button>
            <div class="details-header-title-box">
              <span class="details-header-title">${t('order_hash')}${orderId}</span>
            </div>
            <div style="width: 38px;"></div>
          </header>
          <div class="details-content">
            <div class="empty-wrap">
              <div class="empty-headline">Заказ #${orderId} не найден</div>
              <div class="empty-detail">Возможно, он был перемещен в архив или удален.</div>
            </div>
          </div>
        </div>
      `;
      document.getElementById('btn-back-feed')?.addEventListener('click', closeOrderDetails);
      return;
    }

    const id = Number(order.id || order.order_id);
    const status = (order.status || 'new').toLowerCase();
    const isKitchen = getEffectiveRole() === 'restaurant';
    const total = Number(order.total || 0).toFixed(2);
    const elapsed = formatElapsed(order.created_at);
    const hasCourier = Boolean(order.courier_name || order.courier_phone || (order.courier_id && Number(order.courier_id) > 0));

    let items = [];
    if (Array.isArray(order.items)) items = order.items;
    else if (typeof order.items_json === 'string') {
      try { items = JSON.parse(order.items_json); } catch (e) {}
    }

    let currentStep = 1;
    if (status === 'confirmed' || status === 'accepted') currentStep = 2;
    else if (status === 'preparing') currentStep = 2;
    else if (status === 'ready') currentStep = 3;
    else if (status === 'delivering' || status === 'on_the_way') currentStep = 4;
    else if (status === 'delivered') currentStep = 5;

    const subtotal = items.reduce((acc, it) => acc + (Number(it.price || 0) * Number(it.quantity || 1)), 0);
    const deliveryFee = Math.max(0, Number(order.total || 0) - subtotal);
    const statusLabel = t('status_' + status) || status;

    root.innerHTML = `
      <div class="details-view">
        <!-- Top Executive Frosted Header -->
        <header class="details-header">
          <button class="details-back-icon-btn" id="btn-back-feed" aria-label="${t('details_back')}" title="${t('details_back')}">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m15 18-6-6 6-6"/>
            </svg>
          </button>
          <div class="details-header-title-box">
            <span class="details-header-title">${t('order_hash')}${id}</span>
            ${elapsed ? `<span class="details-header-subtitle">${elapsed}</span>` : ''}
          </div>
          <button class="details-icon-btn" id="btn-copy-link" data-id="${id}" title="${t('details_copy_link')}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
              <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
            </svg>
          </button>
        </header>

        <div class="details-content">
          <!-- 1. Timeline Stepper Card -->
          <div class="details-card timeline-card">
            <div class="details-card-header">
              <span class="details-card-title">${t('details_timeline')}</span>
              <span class="status-tag status-${status}">
                <span class="status-tag-dot"></span>
                <span>${statusLabel}</span>
              </span>
            </div>

            <div class="order-stepper">
              <div class="stepper-step ${currentStep >= 1 ? (currentStep > 1 ? 'is-done' : 'is-active') : ''}">
                <div class="step-circle">${currentStep > 1 ? iconSvg('check', '', 12) : '1'}</div>
                <span class="step-label">${t('stage_confirmed')}</span>
              </div>
              <div class="step-line ${currentStep >= 2 ? 'is-done' : ''}"></div>
              <div class="stepper-step ${currentStep >= 2 ? (currentStep > 2 ? 'is-done' : 'is-active') : ''}">
                <div class="step-circle">${currentStep > 2 ? iconSvg('check', '', 12) : '2'}</div>
                <span class="step-label">${t('stage_cooking')}</span>
              </div>
              <div class="step-line ${currentStep >= 3 ? 'is-done' : ''}"></div>
              <div class="stepper-step ${currentStep >= 3 ? (currentStep > 3 ? 'is-done' : 'is-active') : ''}">
                <div class="step-circle">${currentStep > 3 ? iconSvg('check', '', 12) : '3'}</div>
                <span class="step-label">${t('stage_ready')}</span>
              </div>
              <div class="step-line ${currentStep >= 4 ? 'is-done' : ''}"></div>
              <div class="stepper-step ${currentStep >= 4 ? (currentStep > 4 ? 'is-done' : 'is-active') : ''}">
                <div class="step-circle">${currentStep > 4 ? iconSvg('check', '', 12) : '4'}</div>
                <span class="step-label">${t('stage_delivery')}</span>
              </div>
              <div class="step-line ${currentStep >= 5 ? 'is-done' : ''}"></div>
              <div class="stepper-step ${currentStep >= 5 ? 'is-active' : ''}">
                <div class="step-circle">${currentStep === 5 ? iconSvg('check', '', 12) : '5'}</div>
                <span class="step-label">${t('stage_delivered')}</span>
              </div>
            </div>
          </div>

          ${isKitchen ? `
            <!-- 2. Assigned Courier Card for Kitchen -->
            <div class="details-card courier-card">
              <div class="details-card-header">
                <span class="details-card-title">${t('courier_assigned_title')}</span>
                <span class="details-status-badge ${hasCourier ? 'is-assigned' : 'is-searching'}">
                  ${hasCourier ? '<span class="status-tag-dot" style="background:var(--sky);"></span> Назначен' : '<span class="searching-pulse-dot"></span> Поиск'}
                </span>
              </div>

              ${hasCourier ? `
                <div class="courier-details-strip">
                  <div class="courier-details-left">
                    ${renderCourierAvatar(order.courier_photo, order.courier_name, 38)}
                    <div class="courier-details-info">
                      <span class="courier-details-name">${order.courier_name || 'Курьер'}</span>
                      <span class="courier-details-phone">${order.courier_phone || 'Телефон не указан'}</span>
                    </div>
                  </div>
                  ${order.courier_phone ? `
                    <a class="courier-details-call-btn" href="tel:${order.courier_phone}">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                      <span>${t('courier_call')}</span>
                    </a>
                  ` : ''}
                </div>
              ` : `
                <div class="courier-details-strip is-empty">
                  <span class="searching-pulse-dot"></span>
                  <span class="courier-search-text">${t('courier_searching')}</span>
                </div>
              `}
            </div>
          ` : `
            <!-- Client Info Card for Courier -->
            <div class="details-card client-card">
              <div class="details-card-header">
                <span class="details-card-title">${t('client_info_title')}</span>
              </div>
              <div class="client-row">
                <div class="client-info">
                  <span class="client-name">${order.customer_name || 'Клиент MestiDelivery'}</span>
                  <span class="client-phone">${order.phone || 'Номер не указан'}</span>
                </div>
                ${order.phone ? `
                  <a class="client-call-btn" href="tel:${order.phone}">
                    ${iconSvg("phone", "", 14)}
                    <span>${t('btn_call')}</span>
                  </a>
                ` : ''}
              </div>
            </div>

            <!-- Route Card for Courier -->
            <div class="details-card route-card">
              <div class="details-card-header">
                <span class="details-card-title">${t('route_title')}</span>
                ${order.address ? `
                  <a class="quick-btn" style="height: 30px; font-size: 11px; padding: 0 10px;" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(order.address + ', Mestia')}" target="_blank">
                    ${iconSvg('map', '', 15)} <span>${t('btn_open_map')}</span>
                  </a>
                ` : ''}
              </div>
              <div class="route-block">
                <div class="route-row">
                  <span class="route-dot">${iconSvg("pin", "", 14)}</span>
                  <div class="route-body">
                    <span class="route-type">Ресторан</span>
                    <span class="route-name">${order.restaurant_name || 'MestiDelivery Restaurant'}</span>
                  </div>
                </div>
                <div class="route-row">
                  <span class="route-dot">${iconSvg("home", "", 14)}</span>
                  <div class="route-body">
                    <span class="route-type">Адрес доставки</span>
                    <span class="route-name">${order.address || 'Mestia, Georgia'}</span>
                  </div>
                </div>
              </div>
            </div>
          `}

          <!-- 3. Customer Note (if present) -->
          ${order.comment ? `
            <div class="details-card comment-card">
              <div class="details-card-header">
                <span class="details-card-title">${t('order_notes_title')}</span>
              </div>
              <div class="note-callout" style="margin: 0; font-size: 13px; line-height: 1.5;">
                <strong>${t('note_prefix')}</strong> ${order.comment}
              </div>
            </div>
          ` : ''}

          <!-- 4. Order Ticket & Clean Totals -->
          <div class="details-card ticket-card">
            <div class="details-card-header">
              <span class="details-card-title">${t('ticket_title')}</span>
              <span class="details-badge-muted">${items.length} поз.</span>
            </div>

            <div class="items-table">
              ${items.map(it => {
                const qty = Number(it.quantity || 1);
                return `
                  <div class="item-line">
                    <div class="item-left">
                      <span class="item-qty-badge ${qty > 1 ? 'is-multi' : ''}">${qty}×</span>
                      <span class="item-title">${getTitle(it.name || it.title)}</span>
                    </div>
                    <span class="item-cost">${((Number(it.price || 0)) * qty).toFixed(1)} ₾</span>
                  </div>
                `;
              }).join('')}
            </div>

            <div class="order-totals-box">
              ${deliveryFee > 0 ? `
                <div class="totals-line">
                  <span class="totals-label">Сумма блюд:</span>
                  <span class="totals-val">${subtotal.toFixed(2)} ₾</span>
                </div>
                <div class="totals-line">
                  <span class="totals-label">Доставка:</span>
                  <span class="totals-val">${deliveryFee.toFixed(2)} ₾</span>
                </div>
              ` : ''}
              <div class="totals-line totals-main">
                <span class="totals-main-label">Итого:</span>
                <span class="totals-main-val">${total} ₾</span>
              </div>
            </div>
          </div>

          <!-- 5. Action Buttons -->
          <div class="details-actions-wrap">
            ${renderActionBtn(id, status, isKitchen)}
          </div>
        </div>
      </div>
    `;

    document.getElementById('btn-back-feed')?.addEventListener('click', closeOrderDetails);
    document.getElementById('btn-copy-link')?.addEventListener('click', () => copyOrderLink(id));

    document.querySelectorAll('[data-btn-action="advance"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const target = e.currentTarget.getAttribute('data-target');
        haptic('medium');
        order.status = target;
        renderApp();
        const ok = await api.updateOrderStatus(id, target);
        if (ok) safeStorage.set('mesti_partner_orders', JSON.stringify(state.orders));
        else syncData();
      });
    });

    document.querySelectorAll('[data-btn-action="take"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!state.user?.courier_id) return;
        haptic('medium');
        order.courier_id = state.user.courier_id;
        order.status = 'confirmed';
        renderApp();
        const ok = await api.updateOrderStatus(id, 'confirmed');
        if (ok) syncData();
      });
    });

    document.querySelectorAll('[data-btn-action="cancel"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (window.confirm(t('confirm_cancel'))) {
          haptic('warning');
          order.status = 'cancelled';
          renderApp();
          await api.updateOrderStatus(id, 'cancelled');
        }
      });
    });
  }

  // 12. Full Menu Management View
  function renderMenuTab() {
    let list = state.dishes || [];

    // Filter by Category
    if (state.menuActiveCat === 'stopped') {
      list = list.filter(d => !d.is_available);
    } else if (state.menuActiveCat !== 'all') {
      list = list.filter(d => d.category === state.menuActiveCat);
    }

    // Filter by Search
    if (state.menuSearchQuery) {
      const q = state.menuSearchQuery.toLowerCase();
      list = list.filter(d => {
        const title = getTitle(d.name || d.title).toLowerCase();
        const desc = getTitle(d.description).toLowerCase();
        const ing = (d.ingredients || '').toLowerCase();
        return title.includes(q) || desc.includes(q) || ing.includes(q);
      });
    }

    // Categories array with counts
    const catCounts = {};
    (state.dishes || []).forEach(d => {
      const c = d.category || 'Общее';
      catCounts[c] = (catCounts[c] || 0) + 1;
    });
    const stoppedCount = (state.dishes || []).filter(d => !d.is_available).length;

    const allCategories = ['all', ...(state.menuCategories.length > 0 ? state.menuCategories : Object.keys(catCounts)), 'stopped'];

    return `
      <!-- Top Action & Search -->
      <div class="menu-top-actions">
        <div class="search-box">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--text-muted)">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.3-4.3"></path>
          </svg>
          <input type="text" id="inp-menu-search" class="search-input" placeholder="${t('menu_search_ph')}" value="${state.menuSearchQuery}" />
          ${state.menuSearchQuery ? `<span class="search-clear" id="btn-clear-menu-search">${iconSvg("cross", "", 14)}</span>` : ''}
        </div>
        <button class="btn-add-dish-primary" id="btn-open-add-dish">
          ${iconSvg("plus", "", 15)}
          <span>Добавить</span>
        </button>
      </div>

      <!-- Categories horizontal scroll -->
      <div class="menu-cats-scroll">
        ${allCategories.map(cat => {
          const isAct = state.menuActiveCat === cat;
          let label = cat;
          let count = 0;
          if (cat === 'all') {
            label = t('menu_all_cats');
            count = state.dishes.length;
          } else if (cat === 'stopped') {
            label = t('menu_stopped_cat');
            count = stoppedCount;
          } else {
            count = catCounts[cat] || 0;
          }
          return `
            <button class="cat-pill ${isAct ? 'is-active' : ''}" data-menu-cat="${cat}">
              <span>${label}</span>
              <span class="cat-pill-count">${count}</span>
            </button>
          `;
        }).join('')}
      </div>

      <!-- Dishes Feed Grid -->
      <div class="dish-grid-rich">
        ${list.length === 0 ? `
          <div class="empty-wrap">
            <div class="empty-headline">${t('empty_menu')}</div>
            <div class="empty-detail">Попробуйте выбрать другую категорию или добавить новое блюдо.</div>
          </div>
        ` : list.map(d => renderDishCard(d)).join('')}
      </div>
    `;
  }

  function renderDishCard(dish) {
    const isAvail = dish.is_available !== false;
    const title = getTitle(dish.name || dish.title);
    const desc = getTitle(dish.description);
    const price = Number(dish.price || 0).toFixed(2);
    const imgUrl = dish.image_url || dish.img || '';

    return `
      <div class="dish-card-rich ${!isAvail ? 'is-stopped' : ''}" data-dish-card-id="${dish.id}">
        <div class="dish-img-box">
          ${imgUrl ? `<img src="${imgUrl}" class="dish-img-photo" alt="${title}" onerror="this.style.display='none'" />` : `
            <div class="dish-img-placeholder">${iconSvg("soup", "", 24)}</div>
          `}
          <span class="stock-tag ${isAvail ? 'in-stock' : 'stopped'}" style="position: absolute; bottom: 4px; left: 4px; right: 4px; font-size: 8px; text-align: center; padding: 2px 2px;">
            ${isAvail ? t('dish_in_stock') : t('dish_stopped')}
          </span>
        </div>

        <div class="dish-body-rich">
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 8px;">
            <div class="dish-title-rich">${title}</div>
            <div class="dish-price-rich">${price} ₾</div>
          </div>

          <div class="dish-tags-row">
            ${dish.weight ? `<span class="badge-tag weight">${iconSvg("scale", "", 12)} ${dish.weight}</span>` : ''}
            ${dish.category ? `<span class="badge-tag">${iconSvg("tag", "", 12)} ${dish.category}</span>` : ''}
          </div>

          ${desc ? `<div class="dish-desc-rich">${desc}</div>` : ''}

          <div class="dish-footer-rich">
            <button class="btn-edit-dish" data-edit-dish-id="${dish.id}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
              </svg>
              <span>${t('btn_edit')}</span>
            </button>

            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 11px; color: ${isAvail ? 'var(--emerald)' : 'var(--crimson)'}; font-weight: 700;">
                ${isAvail ? 'В наличии' : 'Стоп-лист'}
              </span>
              <label class="switch" title="В наличии / Стоп-лист">
                <input type="checkbox" class="dish-toggle-switch" data-dish-id="${dish.id}" ${isAvail ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // 13. Dedicated Statistics & Analytics Views (Split by Role)
  function renderKitchenStatsTab() {
    const s = state.statsData || {
      revenue: 0,
      delivered_count: 0,
      active_count: 0,
      cancelled_count: 0,
      avg_check: 0,
      restaurant_net: 0,
      platform_fee: 0,
      daily_chart: [],
      top_dishes: []
    };

    const chartList = s.daily_chart || s.chart || [];
    const maxChartVal = chartList.reduce((acc, p) => Math.max(acc, Number(p.revenue || p.amount || 0)), 1);
    const restShare = s.restaurant_net || (s.revenue ? (Number(s.revenue) * 0.9) : 0);
    const platFee = s.platform_fee || (s.revenue ? (Number(s.revenue) * 0.1) : 0);

    return `
      <div class="stats-container">
        <!-- Period Picker Bar -->
        <div class="period-picker">
          <button class="period-btn ${state.statsPeriod === 'today' ? 'is-selected' : ''}" data-period="today">${t('period_today')}</button>
          <button class="period-btn ${state.statsPeriod === 'week' ? 'is-selected' : ''}" data-period="week">${t('period_week')}</button>
          <button class="period-btn ${state.statsPeriod === 'month' ? 'is-selected' : ''}" data-period="month">${t('period_month')}</button>
          <button class="period-btn ${state.statsPeriod === 'all' ? 'is-selected' : ''}" data-period="all">${t('period_all')}</button>
        </div>

        <!-- 4 KPI Cards Grid -->
        <div class="kpi-grid">
          <div class="kpi-card highlight">
            <span class="kpi-label">${t('kpi_revenue')}</span>
            <span class="kpi-num emerald">${Number(s.revenue || 0).toFixed(1)} ₾</span>
            <span class="kpi-sub">За выбранный период</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('kpi_delivered')}</span>
            <span class="kpi-num">${s.delivered_count || 0}</span>
            <span class="kpi-sub">Успешно доставлено</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('kpi_active')}</span>
            <span class="kpi-num" style="color: var(--amber);">${s.active_count || 0}</span>
            <span class="kpi-sub">Сейчас на кухне</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('kpi_avg_check')}</span>
            <span class="kpi-num">${Number(s.avg_check || 0).toFixed(1)} ₾</span>
            <span class="kpi-sub">Средний чек заказа</span>
          </div>
        </div>

        <!-- Visual Bar Chart Card -->
        <div class="chart-card">
          <div class="chart-head">
            <div>
              <div class="chart-title">${t('chart_sales_dynamic')}</div>
              <div style="font-size: 11px; color: var(--text-muted);">Выручка по дням (₾)</div>
            </div>
            <span class="chart-sum">${Number(s.revenue || 0).toFixed(1)} ₾</span>
          </div>

          <div class="chart-bars-wrap">
            ${chartList.map(bar => {
              const val = Number(bar.revenue || bar.amount || 0);
              const hPercent = maxChartVal > 0 ? Math.max(8, Math.round((val / maxChartVal) * 100)) : 8;
              const isPeak = val === maxChartVal && val > 0;
              const label = bar.day || bar.date || '';
              return `
                <div class="chart-col">
                  <div style="font-size: 10px; font-weight: 700; color: ${val > 0 ? 'var(--emerald)' : 'var(--text-muted)'};">
                    ${val > 0 ? val.toFixed(0) : ''}
                  </div>
                  <div class="bar-cylinder ${val > 0 ? 'has-sales' : ''} ${isPeak ? 'is-peak' : ''}" style="height: ${hPercent}%;"></div>
                  <div class="bar-day-lbl">${label}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <!-- Top Selling Dishes Ranking -->
        <div class="top-dishes-card">
          <div class="chart-head">
            <span class="chart-title">${t('top_dishes_title')}</span>
            <span style="font-size: 11px; color: var(--emerald); font-weight: 800; background: var(--emerald-dim); padding: 2px 8px; border-radius: 6px;">ТОП ПОЗИЦИИ</span>
          </div>

          ${(s.top_dishes && s.top_dishes.length > 0) ? s.top_dishes.map((td, i) => `
            <div class="top-dish-row">
              <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
                <div class="top-rank-circle ${i === 0 ? 'gold' : ''}">${i + 1}</div>
                <div style="min-width: 0;">
                  <div class="top-dish-name">${td.name}</div>
                  <div class="top-dish-qty">${td.count} заказов</div>
                </div>
              </div>
              <div class="top-dish-money">${Number(td.revenue || 0).toFixed(1)} ₾</div>
            </div>
          `).join('') : `
            <div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 14px 0;">
              Данные по лидерам продаж формируются по мере выполнения заказов.
            </div>
          `}
        </div>

        <!-- Financial Settlement Card -->
        <div class="settlement-card">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span class="chart-title">${t('payout_title')}</span>
            <span style="font-size: 10px; padding: 2px 8px; border-radius: 6px; background: rgba(16, 185, 129, 0.15); color: var(--emerald); font-weight: 800; border: 1px solid rgba(16, 185, 129, 0.3);">
              ${t('payout_ready_status')}
            </span>
          </div>

          <div class="settlement-row">
            <span>Общая сумма продаж:</span>
            <span style="font-weight: 800; color: var(--text-primary); font-size: 15px;">${Number(s.revenue || 0).toFixed(2)} ₾</span>
          </div>
          <div class="settlement-row">
            <span>${t('payout_platform_fee')}:</span>
            <span style="color: var(--text-muted);">${Number(platFee).toFixed(2)} ₾</span>
          </div>
          <div class="settlement-row total">
            <span>${t('payout_rest_share')}:</span>
            <span style="color: var(--emerald); font-size: 18px; font-weight: 900;">${Number(restShare).toFixed(2)} ₾</span>
          </div>
        </div>
      </div>
    `;
  }

  function renderCourierStatsTab() {
    const deliveredOrders = state.orders.filter(o => o.status === 'delivered');
    const totalDeliveries = deliveredOrders.length;
    let earnedFees = 0;
    let tipsTotal = 0;
    deliveredOrders.forEach(o => {
      earnedFees += (Number(o.delivery_fee) || 8.0);
      tipsTotal += (Number(o.tips) || 0.0);
    });
    const totalEarnings = earnedFees + tipsTotal;
    const avgDeliveryFee = totalDeliveries > 0 ? (totalEarnings / totalDeliveries).toFixed(1) : '8.0';

    // Group deliveries by day for the chart
    const daysMap = {};
    const now = new Date();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now.getTime() - i * 86400000);
      const dayKey = d.toISOString().slice(5, 10).replace('-', '.');
      const dayNames = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
      const dayName = dayNames[d.getDay()];
      daysMap[dayKey] = { label: `${dayName} ${dayKey}`, count: 0, earnings: 0 };
    }

    deliveredOrders.forEach(o => {
      if (o.created_at) {
        const dKey = o.created_at.slice(5, 10).replace('-', '.');
        if (daysMap[dKey]) {
          daysMap[dKey].count += 1;
          daysMap[dKey].earnings += (Number(o.delivery_fee) || 8.0);
        }
      }
    });

    const chartBars = Object.values(daysMap);
    const maxBarCount = Math.max(...chartBars.map(b => b.count), 1);

    return `
      <div class="stats-container">
        <!-- Period Picker Bar -->
        <div class="period-picker">
          <button class="period-btn ${state.statsPeriod === 'today' ? 'is-selected' : ''}" data-period="today">${t('period_today')}</button>
          <button class="period-btn ${state.statsPeriod === 'week' ? 'is-selected' : ''}" data-period="week">${t('period_week')}</button>
          <button class="period-btn ${state.statsPeriod === 'month' ? 'is-selected' : ''}" data-period="month">${t('period_month')}</button>
          <button class="period-btn ${state.statsPeriod === 'all' ? 'is-selected' : ''}" data-period="all">${t('period_all')}</button>
        </div>

        <!-- 4 Courier KPI Cards Grid -->
        <div class="kpi-grid">
          <div class="kpi-card highlight">
            <span class="kpi-label">${t('courier_kpi_earnings')}</span>
            <span class="kpi-num emerald">${totalEarnings.toFixed(1)} ₾</span>
            <span class="kpi-sub">За период (+доставки и чаевые)</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('courier_kpi_deliveries')}</span>
            <span class="kpi-num">${totalDeliveries}</span>
            <span class="kpi-sub">Успешно вручено клиентам</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('courier_kpi_tips')}</span>
            <span class="kpi-num" style="color: var(--amber);">${tipsTotal.toFixed(1)} ₾</span>
            <span class="kpi-sub">Чаевые от клиентов</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">${t('courier_kpi_avg')}</span>
            <span class="kpi-num">${avgDeliveryFee} ₾</span>
            <span class="kpi-sub">Средний доход за рейс</span>
          </div>
        </div>

        <!-- Courier Delivery Trips Chart -->
        <div class="chart-card">
          <div class="chart-head">
            <div>
              <div class="chart-title">${t('courier_chart_title')}</div>
              <div style="font-size: 11px; color: var(--text-muted);">Количество выполненных доставок по дням</div>
            </div>
            <span class="chart-sum">${totalDeliveries} рейсов</span>
          </div>

          <div class="chart-bars-wrap">
            ${chartBars.map(bar => {
              const hPercent = maxBarCount > 0 ? Math.max(8, Math.round((bar.count / maxBarCount) * 100)) : 8;
              const isPeak = bar.count === maxBarCount && bar.count > 0;
              return `
                <div class="chart-col">
                  <div style="font-size: 10px; font-weight: 700; color: ${bar.count > 0 ? 'var(--emerald)' : 'var(--text-muted)'};">
                    ${bar.count > 0 ? bar.count : ''}
                  </div>
                  <div class="bar-cylinder ${bar.count > 0 ? 'has-sales' : ''} ${isPeak ? 'is-peak' : ''}" style="height: ${hPercent}%;"></div>
                  <div class="bar-day-lbl">${bar.label}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <!-- Recent Delivery Trips List -->
        <div class="top-dishes-card">
          <div class="chart-head">
            <span class="chart-title">${t('courier_trips_title')}</span>
            <span style="font-size: 11px; color: var(--sky); font-weight: 800; background: var(--sky-dim); padding: 2px 8px; border-radius: 6px;">РЕЙСЫ</span>
          </div>

          ${deliveredOrders.length > 0 ? `
            <div class="courier-trips-list">
              ${deliveredOrders.slice(0, 10).map(o => {
                const oid = Number(o.id || o.order_id);
                const fee = (Number(o.delivery_fee) || 8.0).toFixed(2);
                const time = formatElapsed(o.created_at);
                return `
                  <div class="courier-trip-item">
                    <div class="courier-trip-route">
                      <div class="courier-trip-id">Заказ #${oid} • <span style="font-size: 11px; color: var(--emerald); font-weight: 700;">Вручен</span></div>
                      <div class="courier-trip-path">${iconSvg("pin", "", 12)} ${o.restaurant_name || 'Заведение'} ${iconSvg("arrowRight", "", 12)} ${iconSvg("home", "", 12)} ${o.address || 'Местия'}</div>
                      <div style="font-size: 10px; color: var(--text-muted);">${time}</div>
                    </div>
                    <div class="courier-trip-payout">
                      +${fee} ₾
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          ` : `
            <div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 20px 0;">
              Выполненные рейсы будут отображаться здесь после вручения клиентам.
            </div>
          `}
        </div>

        <!-- Balance & Payout Request Card -->
        <div class="settlement-card">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <span class="chart-title">${t('courier_payout_title')}</span>
            <span style="font-size: 10px; padding: 2px 8px; border-radius: 6px; background: rgba(16, 185, 129, 0.15); color: var(--emerald); font-weight: 800; border: 1px solid rgba(16, 185, 129, 0.3);">
              ${t('courier_payout_ready')}
            </span>
          </div>

          <div class="settlement-row">
            <span>Доход за доставку:</span>
            <span style="font-weight: 800; color: var(--text-primary); font-size: 15px;">${earnedFees.toFixed(2)} ₾</span>
          </div>
          <div class="settlement-row">
            <span>Чаевые от клиентов:</span>
            <span style="color: var(--amber); font-weight: 700;">+${tipsTotal.toFixed(2)} ₾</span>
          </div>
          <div class="settlement-row total">
            <span>Итого к выплате:</span>
            <span style="color: var(--emerald); font-size: 18px; font-weight: 900;">${totalEarnings.toFixed(2)} ₾</span>
          </div>

          <button class="btn-primary-action" id="btn-courier-withdraw" style="margin-top: 14px; height: 44px; font-size: 13px;">
            <span>${iconSvg("wallet", "", 15)} ${t('courier_btn_withdraw')}</span>
          </button>
        </div>
      </div>
    `;
  }

  function renderStatsTab() {
    return isKitchenRole() ? renderKitchenStatsTab() : renderCourierStatsTab();
  }

  // 14. Modals
  function renderEditDishModal(dish) {
    const title = getTitle(dish.name || dish.title);
    const desc = getTitle(dish.description);

    return `
      <div class="modal-backdrop" id="modal-backdrop">
        <div class="modal-sheet">
          <div class="modal-header">
            <div class="modal-title">${t('modal_edit_dish_title')}</div>
            <div class="modal-close-btn" id="btn-close-modal">${iconSvg("cross", "", 16)}</div>
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_name')}</label>
            <input type="text" id="inp-edit-name" class="input-field" value="${title}" />
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div class="modal-form-group">
              <label class="modal-label">${t('field_price')}</label>
              <input type="number" step="0.5" id="inp-edit-price" class="input-field" value="${dish.price || 0}" />
            </div>
            <div class="modal-form-group">
              <label class="modal-label">Граммовка</label>
              <input type="text" id="inp-edit-weight" class="input-field" value="${dish.weight || ''}" placeholder="250 г" />
            </div>
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_category')}</label>
            <input type="text" id="inp-edit-category" class="input-field" value="${dish.category || ''}" placeholder="Пицца / Бургеры" />
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_description')}</label>
            <textarea id="inp-edit-desc" class="modal-textarea">${desc}</textarea>
          </div>

          <div class="modal-form-group">
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 0;">
              <span style="font-size: 13px; font-weight: 700; color: var(--text-primary);">${t('field_status')}:</span>
              <label class="switch">
                <input type="checkbox" id="inp-edit-avail" ${dish.is_available ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
          </div>

          <div class="modal-actions-row">
            <button class="btn-primary-action" id="btn-save-edit-dish">
              ${t('btn_save')}
            </button>
            <button class="btn-secondary-danger" id="btn-cancel-edit-dish">
              ${t('btn_cancel_modal')}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function renderAddDishModal() {
    return `
      <div class="modal-backdrop" id="modal-backdrop">
        <div class="modal-sheet">
          <div class="modal-header">
            <div class="modal-title">${t('modal_add_dish_title')}</div>
            <div class="modal-close-btn" id="btn-close-modal">${iconSvg("cross", "", 16)}</div>
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_name')} *</label>
            <input type="text" id="inp-add-name" class="input-field" placeholder="Например: Хачапури по-аджарски" />
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div class="modal-form-group">
              <label class="modal-label">${t('field_price')} *</label>
              <input type="number" step="0.5" id="inp-add-price" class="input-field" placeholder="18.0" />
            </div>
            <div class="modal-form-group">
              <label class="modal-label">Граммовка</label>
              <input type="text" id="inp-add-weight" class="input-field" placeholder="350 г" />
            </div>
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_category')}</label>
            <input type="text" id="inp-add-category" class="input-field" placeholder="Пицца / Бургеры / Выпечка" />
          </div>

          <div class="modal-form-group">
            <label class="modal-label">${t('field_description')}</label>
            <textarea id="inp-add-desc" class="modal-textarea" placeholder="Состав, особенности приготовления..."></textarea>
          </div>

          <div class="modal-actions-row">
            <button class="btn-primary-action" id="btn-submit-add-dish">
              ${t('btn_save')}
            </button>
            <button class="btn-secondary-danger" id="btn-cancel-add-dish">
              ${t('btn_cancel_modal')}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // 15. Rich Partner Profile & Operational Hubs (Split by Role)
  function renderKitchenProfileTab() {
    const username = state.user?.username || 'test_rest';
    const userId = state.user?.id || 1;

    return `
      <div class="feed-container" style="padding-top: 12px;">
        <!-- Group: Prep Time (Sleek Apple Segmented Control) -->
        <div class="settings-group">
          <div class="settings-group-header">${t('prep_time_title')}</div>
          <div class="settings-card" style="padding: 10px 12px;">
            <div class="segmented-control">
              <button class="segment-btn ${state.prepTime === '15' ? 'is-active' : ''}" data-prep="15">15 мин</button>
              <button class="segment-btn ${state.prepTime === '25' ? 'is-active' : ''}" data-prep="25">25 мин</button>
              <button class="segment-btn ${state.prepTime === '40' ? 'is-active' : ''}" data-prep="40">40 мин</button>
              <button class="segment-btn ${state.prepTime === '60' ? 'is-active' : ''}" data-prep="60">60 мин</button>
            </div>
          </div>
        </div>

        <!-- Group: Automation & Alerts -->
        <div class="settings-group">
          <div class="settings-group-header">ОПОВЕЩЕНИЯ И АВТОМАТИЗАЦИЯ</div>
          <div class="settings-card">
            <div class="settings-row">
              <div class="profile-toggle-info">
                <span class="profile-toggle-title">${t('auto_accept_title')}</span>
                <span class="profile-toggle-sub">${t('auto_accept_sub')}</span>
              </div>
              <label class="switch">
                <input type="checkbox" id="chk-auto-accept" ${state.autoAccept ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="settings-row">
              <div class="profile-toggle-info">
                <span class="profile-toggle-title">${t('sound_label')}</span>
                <span class="profile-toggle-sub">Громкий сигнал при поступлении заказа</span>
              </div>
              <label class="switch">
                <input type="checkbox" id="chk-sound-enabled" ${state.soundEnabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
          </div>
        </div>

        <!-- Group: Support & Regulations -->
        <div class="settings-group">
          <div class="settings-group-header">СВЯЗЬ И ПОДДЕРЖКА</div>
          <div class="settings-card">
            <div class="settings-row" style="cursor: pointer;" onclick="window.open('https://t.me/MestiDelivery_Support', '_blank')">
              <div style="display: flex; align-items: center; gap: 12px;">
                <div style="color: var(--brand);">${iconSvg("headset", "", 17)}</div>
                <div style="font-size: 13.5px; font-weight: 600; color: #FFF;">Диспетчер MestiDelivery</div>
              </div>
              <div style="color: var(--text-muted);">${iconSvg("arrowRight", "", 14)}</div>
            </div>
            <div class="settings-row" style="cursor: pointer;" onclick="window.open('tel:+995595000000')">
              <div style="display: flex; align-items: center; gap: 12px;">
                <div style="color: var(--brand);">${iconSvg("phone", "", 17)}</div>
                <div style="font-size: 13.5px; font-weight: 600; color: #FFF;">Горячая линия</div>
              </div>
              <div style="color: var(--text-muted);">${iconSvg("arrowRight", "", 14)}</div>
            </div>
          </div>
        </div>

        ${renderSystemCard()}
      </div>
    `;
  }

  function renderCourierProfileTab() {
    const courierName = state.user?.name || state.user?.username || 'Курьер';
    const transport = state.courierTransport || 'bike';
    const username = state.user?.username || 'courier';
    const courierId = state.user?.courier_id || state.user?.id || 2;

    return `
      <div class="feed-container" style="padding-top: 12px;">
        <!-- Group: Transport Selection (Sleek Segmented Control) -->
        <div class="settings-group">
          <div class="settings-group-header">${t('courier_transport_title')}</div>
          <div class="settings-card" style="padding: 10px 12px;">
            <div class="segmented-control">
              <button class="segment-btn ${transport === 'foot' ? 'is-active' : ''}" data-transport="foot">Пеший</button>
              <button class="segment-btn ${transport === 'bike' ? 'is-active' : ''}" data-transport="bike">Вело</button>
              <button class="segment-btn ${transport === 'scooter' ? 'is-active' : ''}" data-transport="scooter">Скутер</button>
              <button class="segment-btn ${transport === 'car' ? 'is-active' : ''}" data-transport="car">Авто</button>
            </div>
          </div>
        </div>

        <!-- Group: Signals & Feedback -->
        <div class="settings-group">
          <div class="settings-group-header">Оповещения и сигналы</div>
          <div class="settings-card">
            <div class="settings-row">
              <div class="profile-toggle-info">
                <span class="profile-toggle-title">${t('sound_label')}</span>
                <span class="profile-toggle-sub">Громкий сигнал при назначении заказа</span>

              </div>
              <label class="switch">
                <input type="checkbox" id="chk-sound-enabled" ${state.soundEnabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="settings-row">
              <div class="profile-toggle-info">
                <span class="profile-toggle-title">${t('haptic_title')}</span>
                <span class="profile-toggle-sub">${t('haptic_sub')}</span>
              </div>
              <label class="switch">
                <input type="checkbox" id="chk-haptic-enabled" ${state.hapticEnabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
          </div>
        </div>

        <!-- Group: Support & Regulations -->
        <div class="settings-group">
          <div class="settings-group-header">Поддержка курьеров</div>
          <div class="settings-card">
            <div class="settings-row" style="cursor: pointer;" onclick="window.open('https://t.me/MestiDelivery_Support', '_blank')">
              <div style="display: flex; align-items: center; gap: 10px;">
                <div style="color: var(--brand);">${iconSvg("headset", "", 18)}</div>
                <div style="font-size: 13.5px; font-weight: 600; color: #FFF;">Диспетчер смены Telegram</div>
              </div>
              <div style="color: var(--text-muted);">${iconSvg("arrowRight", "", 14)}</div>
            </div>
            <div class="settings-row" style="cursor: pointer;" onclick="window.open('tel:+995595000000')">
              <div style="display: flex; align-items: center; gap: 10px;">
                <div style="color: var(--crimson);">${iconSvg("alert", "", 18)}</div>
                <div style="font-size: 13.5px; font-weight: 600; color: #FFF;">Форс-мажор в пути (Срочно)</div>
              </div>
              <div style="color: var(--text-muted);">${iconSvg("arrowRight", "", 14)}</div>
            </div>
          </div>
        </div>

        ${renderSystemCard()}
      </div>
    `;
  }
  function renderSystemCard() {
    return `
      <div class="settings-group">
        <div class="settings-group-header">ЯЗЫК ИНТЕРФЕЙСА</div>
        <div class="settings-card" style="padding: 10px 12px;">
          <div class="segmented-control">
            <button class="segment-btn ${currentLang === 'ru' ? 'is-active' : ''}" data-set-lang="ru">Русский</button>
            <button class="segment-btn ${currentLang === 'en' ? 'is-active' : ''}" data-set-lang="en">English</button>
            <button class="segment-btn ${currentLang === 'ka' ? 'is-active' : ''}" data-set-lang="ka">ქართული</button>
          </div>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 10px; margin: 18px 16px 36px 16px;">
        <button class="btn-clean-secondary" id="btn-clear-cache">
          ${iconSvg("refresh", "", 14)}
          <span>${t('btn_clear_cache')}</span>
        </button>
        <button class="btn-clean-danger" id="btn-logout">
          <span>${t('logout')}</span>
        </button>
        <div class="app-version-footnote">
          MestiDelivery Partners • v8.1
        </div>
      </div>
    `;
  }

  function renderProfileTab() {
    return isKitchenRole() ? renderKitchenProfileTab() : renderCourierProfileTab();
  }

  function renderNotRegistered(root) {
    const tgUser = state.notRegisteredUser;
    const name = tgUser?.first_name || tgUser?.username || '';
    root.innerHTML = `
      <div class="login-wrap">
        <div class="login-box" style="text-align: center;">
          <div style="width: 56px; height: 56px; border-radius: 16px; background: var(--amber-dim); border: 1px solid var(--amber); margin: 0 auto 8px; display: flex; align-items: center; justify-content: center; color: var(--amber); box-shadow: 0 4px 16px var(--amber-glow);">
            ${iconSvg("alert", "", 28)}
          </div>
          <div style="font-size: 19px; font-weight: 800; color: var(--text-primary);">
            ${t('not_reg_title')}
          </div>
          <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.5;">
            ${name ? `Привет, ${name}! ` : ''}${t('not_reg_sub')}
          </div>
          <a class="btn-primary-action" href="https://t.me/MestiDelivery_Robot" target="_blank" style="text-decoration: none; margin-top: 8px;">
            ${t('not_reg_btn')}
          </a>
          <button class="btn-secondary-danger" id="btn-show-login" style="border-color: var(--border); color: var(--text-muted); margin-top: 6px;">
            ${t('not_reg_or_login')}
          </button>
        </div>
      </div>
    `;

    document.getElementById('btn-show-login')?.addEventListener('click', () => {
      state.showManualLogin = true;
      renderApp();
    });
  }

  function renderLogin(root) {
    root.innerHTML = `
      <div class="login-wrap">
        <div class="login-box">
          <div>
            <div style="font-size: 19px; font-weight: 800; color: var(--text-primary); margin-bottom: 4px;">
              ${t('login_title')}
            </div>
            <div style="font-size: 13px; color: var(--text-secondary);">
              ${t('login_sub')}
            </div>
          </div>

          <input type="text" id="inp-u" class="input-field" placeholder="Логин (например, test_rest)" />
          <input type="password" id="inp-p" class="input-field" placeholder="Пароль" />

          <button class="btn-primary-action" id="btn-login-submit">
            ${t('login_btn')}
          </button>
        </div>
      </div>
    `;

    document.getElementById('btn-login-submit')?.addEventListener('click', async () => {
      const u = document.getElementById('inp-u')?.value.trim();
      const p = document.getElementById('inp-p')?.value.trim();
      if (!u || !p) return;
      try {
        haptic('light');
        const user = await api.loginWithCredentials(u, p);
        state.user = user;
        safeStorage.set('mesti_partner_user', JSON.stringify(user));
        renderApp();
        syncData();
      } catch (err) {
        haptic('error');
        alert(err.message || 'Ошибка авторизации');
      }
    });
  }

  // 16. Event Binding
  function bindEvents() {
    document.getElementById('btn-shift')?.addEventListener('click', () => {
      haptic('light');
      state.isOnline = !state.isOnline;
      safeStorage.set('partner_online', String(state.isOnline));
      renderApp();
    });

    document.getElementById('btn-profile-shift')?.addEventListener('click', () => {
      haptic('light');
      state.isOnline = !state.isOnline;
      safeStorage.set('partner_online', String(state.isOnline));
      renderApp();
    });

    document.getElementById('btn-sync')?.addEventListener('click', async () => {
      haptic('light');
      await syncData();
    });

    document.getElementById('btn-sound')?.addEventListener('click', () => {
      haptic('light');
      state.soundEnabled = !state.soundEnabled;
      safeStorage.set('partner_sound', String(state.soundEnabled));
      if (state.soundEnabled) playNewOrderChime();
      renderApp();
    });

    // Profile Hub Events
    document.querySelectorAll('[data-prep]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const prep = e.currentTarget.getAttribute('data-prep');
        if (prep) {
          haptic('medium');
          state.prepTime = prep;
          safeStorage.set('partner_prep_time', prep);
          renderApp();
          showToast(`Время приготовления: ${prep} минут`);
        }
      });
    });

    document.getElementById('chk-auto-accept')?.addEventListener('change', (e) => {
      haptic('light');
      state.autoAccept = e.target.checked;
      safeStorage.set('partner_auto_accept', String(state.autoAccept));
      showToast(state.autoAccept ? 'Авто-приём заказов включён' : 'Авто-приём заказов выключен');
    });

    document.getElementById('chk-sound-enabled')?.addEventListener('change', (e) => {
      haptic('light');
      state.soundEnabled = e.target.checked;
      safeStorage.set('partner_sound', String(state.soundEnabled));
      if (state.soundEnabled) playNewOrderChime();
      renderApp();
    });

    document.getElementById('btn-test-chime')?.addEventListener('click', () => {
      haptic('success');
      playNewOrderChime();
    });

    document.getElementById('chk-haptic-enabled')?.addEventListener('change', (e) => {
      state.hapticEnabled = e.target.checked;
      safeStorage.set('partner_haptic', String(state.hapticEnabled));
      if (state.hapticEnabled) haptic('heavy');
    });

    document.getElementById('btn-save-contacts')?.addEventListener('click', () => {
      const sched = document.getElementById('inp-schedule')?.value.trim();
      const phone = document.getElementById('inp-kitchen-phone')?.value.trim();
      if (sched) {
        state.kitchenSchedule = sched;
        safeStorage.set('partner_schedule', sched);
      }
      if (phone) {
        state.kitchenPhone = phone;
        safeStorage.set('partner_kitchen_phone', phone);
      }
      haptic('success');
      showToast(t('settings_saved_toast'));
    });

    // Courier Transport Selector
    document.querySelectorAll('[data-transport]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tr = e.currentTarget.getAttribute('data-transport');
        if (tr) {
          haptic('medium');
          state.courierTransport = tr;
          safeStorage.set('courier_transport', tr);
          renderApp();
          showToast('Транспорт курьера обновлен');
        }
      });
    });


    // Courier Balance Withdrawal
    document.getElementById('btn-courier-withdraw')?.addEventListener('click', () => {
      haptic('success');
      showToast('Запрос на вывод баланса сформирован!');
      setTimeout(() => {
        window.open('https://t.me/MestiDelivery_Support?text=' + encodeURIComponent('Здравствуйте! Прошу вывести заработанный баланс курьера ' + (state.user?.name || state.user?.username || '')), '_blank');
      }, 700);
    });

    // FAQ Accordion click
    document.querySelectorAll('.faq-question').forEach(q => {
      q.addEventListener('click', (e) => {
        haptic('light');
        const item = e.currentTarget.closest('.faq-item');
        if (item) {
          item.classList.toggle('is-open');
        }
      });
    });

    // Clear Cache Button
    document.getElementById('btn-clear-cache')?.addEventListener('click', async () => {
      haptic('warning');
      const keepUser = safeStorage.get('mesti_partner_user');
      const keepLang = safeStorage.get('partner_lang');
      safeStorage.clear();
      if (keepUser) safeStorage.set('mesti_partner_user', keepUser);
      if (keepLang) safeStorage.set('partner_lang', keepLang);
      showToast(t('cache_cleared_toast'));
      await syncData();
    });

    // Logout
    document.getElementById('btn-logout')?.addEventListener('click', () => {
      haptic('warning');
      if (window.confirm('Вы действительно хотите выйти из аккаунта?')) {
        safeStorage.clear();
        state.user = null;
        state.orders = [];
        state.dishes = [];
        renderApp();
      }
    });

    // Single pill chips filter row events
    document.querySelectorAll('[data-nav-action]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const act = e.currentTarget.getAttribute('data-nav-action');
        haptic('light');
        if (act === 'kitchen-all') {
          state.subTab = 'active';
          state.statusFilter = 'all';
        } else if (act === 'kitchen-new') {
          state.subTab = 'active';
          state.statusFilter = 'new';
        } else if (act === 'kitchen-cooking') {
          state.subTab = 'active';
          state.statusFilter = 'cooking';
        } else if (act === 'kitchen-ready') {
          state.subTab = 'active';
          state.statusFilter = 'ready';
        } else if (act === 'radar') {
          state.subTab = 'radar';
        } else if (act === 'courier-my') {
          state.subTab = 'active';
        } else if (act === 'history') {
          state.subTab = 'history';
        }
        renderApp();
      });
    });

    // Feed Search
    const searchInp = document.getElementById('inp-search');
    if (searchInp) {
      searchInp.addEventListener('input', (e) => {
        state.searchQuery = e.target.value;
        renderApp();
        const freshInp = document.getElementById('inp-search');
        if (freshInp) {
          freshInp.focus();
          freshInp.setSelectionRange(freshInp.value.length, freshInp.value.length);
        }
      });
    }

    document.getElementById('btn-clear-search')?.addEventListener('click', () => {
      haptic('light');
      state.searchQuery = '';
      renderApp();
    });

    // Menu Search
    const menuSearchInp = document.getElementById('inp-menu-search');
    if (menuSearchInp) {
      menuSearchInp.addEventListener('input', (e) => {
        state.menuSearchQuery = e.target.value;
        renderApp();
        const freshMenuInp = document.getElementById('inp-menu-search');
        if (freshMenuInp) {
          freshMenuInp.focus();
          freshMenuInp.setSelectionRange(freshMenuInp.value.length, freshMenuInp.value.length);
        }
      });
    }

    document.getElementById('btn-clear-menu-search')?.addEventListener('click', () => {
      haptic('light');
      state.menuSearchQuery = '';
      renderApp();
    });

    // Navigation Tabs
    document.querySelectorAll('[data-nav]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const nav = e.currentTarget.getAttribute('data-nav');
        if (nav && nav !== state.currentTab) {
          haptic('light');
          state.currentTab = nav;
          renderApp();
          if (nav === 'menu') await api.fetchMenu();
          if (nav === 'stats') await api.fetchStats(state.statsPeriod);
          renderApp();
        }
      });
    });

    // Feed Category Filter Pills
    document.querySelectorAll('[data-filter]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const filter = e.currentTarget.getAttribute('data-filter');
        if (filter) {
          haptic('light');
          state.statusFilter = filter;
          renderApp();
        }
      });
    });

    // Menu Category Pills
    document.querySelectorAll('[data-menu-cat]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const cat = e.currentTarget.getAttribute('data-menu-cat');
        if (cat) {
          haptic('light');
          state.menuActiveCat = cat;
          renderApp();
        }
      });
    });

    // Open Details Buttons
    document.querySelectorAll('[data-open-id]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-open-id');
        if (id) openOrderDetails(id);
      });
    });

    // Sub-Tabs
    document.querySelectorAll('[data-sub]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const sub = e.currentTarget.getAttribute('data-sub');
        if (sub && sub !== state.subTab) {
          haptic('light');
          state.subTab = sub;
          renderApp();
        }
      });
    });

    // Stats Period Selector
    document.querySelectorAll('[data-period]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const p = e.currentTarget.getAttribute('data-period');
        if (p && p !== state.statsPeriod) {
          haptic('light');
          state.statsPeriod = p;
          renderApp();
          await api.fetchStats(p);
          renderApp();
        }
      });
    });

    // Language Selector
    document.querySelectorAll('[data-set-lang]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const newLang = e.currentTarget.getAttribute('data-set-lang');
        if (newLang && I18N[newLang]) {
          haptic('light');
          currentLang = newLang;
          safeStorage.set('partner_lang_manual', newLang);
          safeStorage.set('partner_lang', newLang);
          renderApp();
        }
      });
    });

    // Action Buttons on Order Cards
    document.querySelectorAll('[data-btn-action="advance"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = Number(e.currentTarget.getAttribute('data-id'));
        const target = e.currentTarget.getAttribute('data-target');
        if (!id || !target) return;
        haptic('medium');
        const order = state.orders.find(o => Number(o.id || o.order_id) === id);
        if (order) {
          order.status = target;
          renderApp();
        }
        const ok = await api.updateOrderStatus(id, target);
        if (ok) safeStorage.set('mesti_partner_orders', JSON.stringify(state.orders));
        else syncData();
      });
    });

    document.querySelectorAll('[data-btn-action="take"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = Number(e.currentTarget.getAttribute('data-id'));
        if (!id || !state.user?.courier_id) return;
        haptic('medium');
        const order = state.orders.find(o => Number(o.id || o.order_id) === id);
        if (order) {
          order.courier_id = state.user.courier_id;
          order.status = 'confirmed';
          renderApp();
        }
        const ok = await api.updateOrderStatus(id, 'confirmed');
        if (ok) syncData();
      });
    });

    document.querySelectorAll('[data-btn-action="cancel"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = Number(e.currentTarget.getAttribute('data-id'));
        if (!id) return;
        if (window.confirm(t('confirm_cancel'))) {
          haptic('warning');
          const order = state.orders.find(o => Number(o.id || o.order_id) === id);
          if (order) {
            order.status = 'cancelled';
            renderApp();
          }
          await api.updateOrderStatus(id, 'cancelled');
        }
      });
    });

    // Dish Switch Toggles in Menu
    document.querySelectorAll('.dish-toggle-switch').forEach(chk => {
      chk.addEventListener('change', async (e) => {
        const id = e.target.getAttribute('data-dish-id');
        const dish = (state.dishes || []).find(d => String(d.id) === String(id));
        if (!dish) return;

        haptic('light');
        dish.is_available = e.target.checked;
        safeStorage.set('mesti_partner_menu', JSON.stringify(state.dishes));
        renderApp();
        await api.toggleDishAvailability(id, dish.is_available);
      });
    });

    // Edit Dish Modal Opener
    document.querySelectorAll('[data-edit-dish-id]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-edit-dish-id');
        const dish = (state.dishes || []).find(d => String(d.id) === String(id));
        if (dish) {
          haptic('light');
          state.editingDish = dish;
          renderApp();
        }
      });
    });

    // Add Dish Modal Opener
    document.getElementById('btn-open-add-dish')?.addEventListener('click', () => {
      haptic('light');
      state.isAddingDish = true;
      renderApp();
    });

    // Modal Close
    document.getElementById('btn-close-modal')?.addEventListener('click', () => {
      state.editingDish = null;
      state.isAddingDish = false;
      document.body.classList.remove('modal-open');
      renderApp();
    });

    const modalBackdropEl = document.getElementById('modal-backdrop');
    if (modalBackdropEl) {
      modalBackdropEl.addEventListener('click', (e) => {
        if (e.target === modalBackdropEl) {
          state.editingDish = null;
          state.isAddingDish = false;
          document.body.classList.remove('modal-open');
          renderApp();
        }
      });
    }

    document.getElementById('btn-cancel-edit-dish')?.addEventListener('click', () => {
      state.editingDish = null;
      renderApp();
    });

    document.getElementById('btn-cancel-add-dish')?.addEventListener('click', () => {
      state.isAddingDish = false;
      renderApp();
    });

    // Save Edited Dish
    document.getElementById('btn-save-edit-dish')?.addEventListener('click', async () => {
      if (!state.editingDish) return;
      const name = document.getElementById('inp-edit-name')?.value.trim();
      const price = parseFloat(document.getElementById('inp-edit-price')?.value || '0');
      const weight = document.getElementById('inp-edit-weight')?.value.trim();
      const category = document.getElementById('inp-edit-category')?.value.trim();
      const desc = document.getElementById('inp-edit-desc')?.value.trim();
      const isAvail = document.getElementById('inp-edit-avail')?.checked;

      if (!name || isNaN(price)) {
        alert('Укажите название и корректную цену блюда');
        return;
      }

      haptic('medium');
      state.editingDish.name = name;
      state.editingDish.price = price;
      state.editingDish.weight = weight;
      state.editingDish.category = category;
      state.editingDish.description = desc;
      state.editingDish.is_available = isAvail;

      safeStorage.set('mesti_partner_menu', JSON.stringify(state.dishes));
      const dishToSave = { ...state.editingDish };
      state.editingDish = null;
      renderApp();
      showToast(t('dish_saved_toast'));

      await api.updateDish(dishToSave);
      await api.fetchMenu();
      renderApp();
    });

    // Submit New Dish
    document.getElementById('btn-submit-add-dish')?.addEventListener('click', async () => {
      const name = document.getElementById('inp-add-name')?.value.trim();
      const price = parseFloat(document.getElementById('inp-add-price')?.value || '0');
      const weight = document.getElementById('inp-add-weight')?.value.trim();
      const category = document.getElementById('inp-add-category')?.value.trim();
      const desc = document.getElementById('inp-add-desc')?.value.trim();

      if (!name || isNaN(price) || price <= 0) {
        alert('Заполните обязательные поля: название и цену блюда');
        return;
      }

      haptic('success');
      const newDish = {
        name,
        price,
        weight,
        category: category || 'Основное',
        description: desc,
        is_available: true,
        restaurant_id: state.user?.restaurant_id || 'test_rest_01'
      };

      state.isAddingDish = false;
      renderApp();
      showToast(t('dish_created_toast'));

      await api.createDish(newDish);
      await api.fetchMenu();
      renderApp();
    });
  }

  // 17. Data Synchronization
  async function syncData() {
    if (state.isSyncing) return;
    state.isSyncing = true;
    const syncBtn = document.getElementById('btn-sync');
    if (syncBtn) syncBtn.classList.add('is-spinning');

    try {
      const orders = await api.fetchOrders();
      if (Array.isArray(orders)) {
        const oldActiveIds = new Set(
          state.orders
            .filter(o => o.status !== 'delivered' && o.status !== 'cancelled')
            .map(o => Number(o.id || o.order_id))
        );

        const hasFreshOrder = orders.some(o => {
          const id = Number(o.id || o.order_id);
          const isAct = o.status !== 'delivered' && o.status !== 'cancelled';
          return isAct && !oldActiveIds.has(id);
        });

        state.orders = orders;
        safeStorage.set('mesti_partner_orders', JSON.stringify(orders));

        if (hasFreshOrder) {
          haptic('heavy');
          playNewOrderChime();
        }

        // Auto-Accept for kitchen if enabled
        if (state.autoAccept && (state.user?.role === 'restaurant_admin' || state.user?.restaurant_id)) {
          orders.forEach(async o => {
            if (o.status === 'new' || o.status === 'pending') {
              const oid = Number(o.id || o.order_id);
              o.status = 'confirmed';
              await api.updateOrderStatus(oid, 'confirmed');
            }
          });
        }
      }

      if (state.currentTab === 'menu') {
        await api.fetchMenu();
      } else if (state.currentTab === 'stats') {
        await api.fetchStats(state.statsPeriod);
      }
    } catch (e) {
      console.warn('Sync error:', e);
    } finally {
      state.isSyncing = false;
      if (syncBtn) syncBtn.classList.remove('is-spinning');
      renderApp();
    }
  }

  // 18. Application Bootstrap
  async function init() {
    applySafeAreas();

    const params = new URLSearchParams(window.location.search);
    const ordId = params.get('order_id');
    if (ordId) {
      state.selectedOrderId = Number(ordId);
      const tg = getTG();
      if (tg?.BackButton) {
        tg.BackButton.show();
        tg.BackButton.onClick(closeOrderDetails);
      }
    }

    // Clean up misleading URL query parameter if user is authenticated kitchen
    if (state.user && isKitchenRole()) {
      try {
        const u = new URL(window.location.href);
        if (u.searchParams.get('role') === 'courier') {
          u.searchParams.delete('role');
          window.history.replaceState({}, '', u.toString());
        }
      } catch (e) {}
    }

    renderApp();

    if (!state.user) {
      const tgUser = extractTelegramUser();
      if (tgUser) {
        const authRes = await api.autoTelegramAuth(tgUser);
        if (authRes?.ok && authRes.user) {
          state.user = authRes.user;
          safeStorage.set('mesti_partner_user', JSON.stringify(authRes.user));
          state.notRegisteredUser = null;
        } else if (authRes?.not_registered) {
          state.notRegisteredUser = tgUser;
        }
      }
    }

    renderApp();

    if (state.user) {
      await syncData();
      if (state.currentTab === 'menu' || state.user.role === 'restaurant_admin') {
        api.fetchMenu().catch(() => {});
      }
    }

    // Fast 3s polling for real-time order reactivity
    setInterval(() => {
      if (state.user && !state.isSyncing) {
        syncData();
      }
    }, 3000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
