# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement

---

## In Progress

*(empty)*

---

## Planned

### Features

#### [P1] [FEAT] Investment Search Agent (Cloud ☁️)
A new agent that actively searches for investment opportunities using public APIs.
Follows the existing skills architecture — each search strategy is a skill.

**Skill: Stock Screener**
- Search stocks by region (Europe, US, Emerging Markets, ...)
- Filter by strategy (value, growth, dividend, momentum)
- Cost-aware: flag high transaction costs or illiquid markets
- Output: ranked list with P/E, dividend yield, sector, region

**Skill: Fund Screener**
- Search ETFs and active funds
- Heavy focus on fund costs (TER — Total Expense Ratio)
- Performance comparison (1y, 3y, 5y vs. benchmark)
- Filter by region, sector, or investment theme (ESG, technology, emerging markets, ...)
- Output: ranked list with TER, performance, AUM, theme match

→ [GitHub Issue #1](https://github.com/esc1899/wealth_management/issues/1)

### Improvements
<!-- UI/UX, performance, code quality -->

### Bugs
<!-- Known bugs -->

---

## Ideas / Later

<!-- Rough ideas without a concrete plan -->

---

## Done

<!-- Completed items with date and commit/PR reference -->
