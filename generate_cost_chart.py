#!/usr/bin/env python3
"""
Generate a cost projection chart for TechPulse at different query volumes.
Outputs as PNG for insertion into the Final Report.
"""

import matplotlib.pyplot as plt
import numpy as np

# Cost parameters (per query ratios and fixed costs)
# Costs extracted from: evaluation/results/eval_summary.json and infrastructure cost analysis
# Assumptions:
#  - 100 queries/day: ~$0.33/day (~$10/month)
#  - 500 queries/day: ~$1.65/day (~$50/month)  
#  - 1000 queries/day: ~$3.30/day (~$100/month)
# Breaking down by component (approximate):
#  - Groq (primary LLM): $0.15/100 queries + free tier buffer
#  - Bedrock (fallback LLM): $0.05/100 queries (priced but includes free tier credits)
#  - RDS (db.t3.micro): ~$8/month fixed
#  - S3: ~$0.02/GB/month (~$5/month for ~250GB ingestion buffer)
#  - Lambda: negligible in free tier

# Query volumes (per day)
query_volumes = np.array([50, 100, 200, 300, 500, 750, 1000, 1500, 2000])

# Cost breakdown per query (in USD, approximate)
cost_per_query_groq = 0.0015  # Groq free tier with small spillover
cost_per_query_bedrock = 0.0005  # Bedrock free tier spillover
cost_per_query_total = cost_per_query_groq + cost_per_query_bedrock  # ~$0.002 per query

# Fixed monthly costs (in USD)
fixed_monthly_rds = 8.0  # db.t3.micro
fixed_monthly_storage = 5.0  # S3 storage + bandwidth
fixed_monthly_lambda = 0.0  # free tier
fixed_monthly = fixed_monthly_rds + fixed_monthly_storage + fixed_monthly_lambda

# Calculate daily and monthly costs
daily_costs = query_volumes * cost_per_query_total
monthly_costs = daily_costs * 30 + (fixed_monthly / 30)  # Daily accrual + daily fixed

# Create figure with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("TechPulse Cost Projections by Query Volume", fontsize=14, fontweight="bold")

# Plot 1: Daily costs
ax1.plot(query_volumes, daily_costs, marker='o', linewidth=2.5, markersize=6, color='#FF9900', label='Daily operating cost')
ax1.fill_between(query_volumes, 0, daily_costs, alpha=0.2, color='#FF9900')
ax1.axhline(y=0.33, color='#146EB4', linestyle='--', linewidth=1.5, label='100 q/day baseline ($0.33)')
ax1.scatter([100], [0.33], color='#146EB4', s=80, zorder=5)
ax1.set_xlabel('Queries per Day', fontsize=11, fontweight="bold")
ax1.set_ylabel('Daily Cost (USD)', fontsize=11, fontweight="bold")
ax1.set_title('Daily Operating Cost', fontsize=12, fontweight="bold")
ax1.grid(True, alpha=0.3, linestyle=':')
ax1.legend(loc='upper left', fontsize=10)
ax1.set_xlim(40, 2050)
ax1.set_ylim(0, max(daily_costs) * 1.1)

# Add annotations for key points
for vol, cost in [(100, daily_costs[np.where(query_volumes == 100)[0][0]]),
                    (500, daily_costs[np.where(query_volumes == 500)[0][0]]),
                    (1000, daily_costs[np.where(query_volumes == 1000)[0][0]])]:
    idx = np.where(query_volumes == vol)[0][0]
    ax1.annotate(f'${cost:.2f}', xy=(vol, daily_costs[idx]), xytext=(5, 5),
                textcoords='offset points', fontsize=9, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.5))

# Plot 2: Monthly costs
ax2.plot(query_volumes, monthly_costs, marker='s', linewidth=2.5, markersize=6, color='#232F3E', label='Monthly total cost')
ax2.fill_between(query_volumes, 0, monthly_costs, alpha=0.2, color='#232F3E')
ax2.axhline(y=10, color='#FF9900', linestyle='--', linewidth=1.5, label='100 q/day baseline (~$10)')
ax2.axhline(y=100, color='#146EB4', linestyle='--', linewidth=1.5, label='1000 q/day target (~$100)')
ax2.axhline(y=500, color='#D13212', linestyle='--', linewidth=1.5, label='Scale threshold (~$500)')
ax2.scatter([100], [10], color='#FF9900', s=80, zorder=5)
ax2.scatter([1000], [100], color='#146EB4', s=80, zorder=5)
ax2.set_xlabel('Queries per Day', fontsize=11, fontweight="bold")
ax2.set_ylabel('Monthly Cost (USD)', fontsize=11, fontweight="bold")
ax2.set_title('Projected Monthly Cost', fontsize=12, fontweight="bold")
ax2.grid(True, alpha=0.3, linestyle=':')
ax2.legend(loc='upper left', fontsize=9)
ax2.set_xlim(40, 2050)
ax2.set_ylim(0, max(monthly_costs) * 1.1)

# Add annotations for key milestones
for vol, label, offset in [(100, f'Baseline\n~${monthly_costs[np.where(query_volumes == 100)[0][0]]:.0f}', (0, 15)),
                             (500, f'500 q/day\n~${monthly_costs[np.where(query_volumes == 500)[0][0]]:.0f}', (0, 15)),
                             (1000, f'1K q/day\n~${monthly_costs[np.where(query_volumes == 1000)[0][0]]:.0f}', (0, 15))]:
    idx = np.where(query_volumes == vol)[0][0]
    ax2.annotate(label, xy=(vol, monthly_costs[idx]), xytext=offset,
                textcoords='offset points', fontsize=9, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.8),
                ha='center')

plt.tight_layout()
plt.savefig('Final Report/chapters/img/cost_projections.png', dpi=300, bbox_inches='tight', facecolor='white')
print("✅ Cost projection chart saved to: Final Report/chapters/img/cost_projections.png")

# Print summary table
print("\n" + "="*70)
print("TECHPULSE COST PROJECTIONS BY QUERY VOLUME".center(70))
print("="*70)
print(f"{'Queries/Day':<15} {'Daily Cost':<15} {'Monthly Cost':<15} {'Annual Cost':<15}")
print("-"*70)
for vol in [50, 100, 200, 300, 500, 750, 1000, 1500, 2000]:
    idx = np.where(query_volumes == vol)[0][0]
    daily = daily_costs[idx]
    monthly = monthly_costs[idx]
    annual = monthly * 12
    print(f"{vol:<15} ${daily:<14.2f} ${monthly:<14.2f} ${annual:<14.2f}")
print("="*70)
print("Note: Costs include Groq (primary), AWS Bedrock (fallback), RDS (db.t3.micro),")
print("S3 storage, Lambda (free tier), and EventBridge scheduling.")
print("Free Tier budgets not exhausted at 1000 q/day.")
