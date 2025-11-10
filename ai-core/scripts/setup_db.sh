#!/usr/bin/env bash
# Setup Prisma database
set -euo pipefail

cd "$(dirname "$0")/.."

echo "🔧 Setting up Prisma database..."

# Generate Prisma client
echo "Generating Prisma client..."
prisma generate --schema=schema.prisma

# Optional: Push schema to database
read -p "Push schema to database? (yes/no) " answer
if [ "$answer" == "yes" ]; then
    echo "Pushing schema to PostgreSQL..."
    prisma db push --schema=schema.prisma
    echo "✅ Database schema updated"
else
    echo "⏭️  Skipped database push"
fi

echo "✅ Prisma setup complete!"
