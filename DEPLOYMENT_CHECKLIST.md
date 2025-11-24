# Deployment Day Checklist

**Quick reference for library migration deployment**

---

## Before You Start

```bash
# 1. Backup MongoDB
mongodump --db vandalizer --out /backup/pre-migration-$(date +%Y%m%d)

# 2. Verify backup
ls -lh /backup/pre-migration-*/vandalizer/
```

---

## Deploy Code

```bash
# 1. Pull latest code
git pull origin main

# 2. Restart app
sudo systemctl restart vandalizer  # or your app service name

# 3. Test basic functionality
curl http://localhost:5000/health  # or your health check endpoint
```

---

## Run Migration

```bash
cd /path/to/vandalizer

# STEP 1: Dry run (preview changes)
python -m app.utilities.migrate_to_libraries --dry-run

# STEP 2: Review output - look for:
#   - User count seems correct
#   - Orphaned data count is reasonable
#   - No unexpected errors

# STEP 3: Run actual migration
python -m app.utilities.migrate_to_libraries

# STEP 4: Verify success
python -m app.utilities.migrate_to_libraries --verify-only
```

---

## Expected Output

### ✅ Success Looks Like:
```
✅ Migration completed successfully with no issues!
✅ All users have personal libraries
✅ All SearchSets are in libraries
✅ All Workflows are in libraries
```

### ⚠️ Issues to Watch For:
- Any ❌ errors in output
- Large number of orphaned items (>100)
- Users without personal libraries

---

## Quick Tests

```bash
# 1. Check MongoDB
mongo vandalizer --eval "db.library.count()"
mongo vandalizer --eval "db.library_item.count()"

# 2. Test frontend
# - Log in as test user
# - Navigate to library view
# - Verify search_sets appear
# - Test old search_set functionality

# 3. Check logs
tail -f /var/log/vandalizer/app.log  # adjust path as needed
```

---

## Rollback (if needed)

```bash
# Stop app
sudo systemctl stop vandalizer

# Restore database
mongorestore --db vandalizer /backup/pre-migration-YYYYMMDD/vandalizer

# Restart app
sudo systemctl start vandalizer
```

---

## Commands Reference

```bash
# Dry run
python -m app.utilities.migrate_to_libraries --dry-run

# Actual migration
python -m app.utilities.migrate_to_libraries

# Verify only
python -m app.utilities.migrate_to_libraries --verify-only

# Custom fallback user
python -m app.utilities.migrate_to_libraries --fallback-email admin@example.com

# Help
python -m app.utilities.migrate_to_libraries --help
```

---

## Post-Deployment

- [ ] Monitor logs for 1 hour
- [ ] Test with 3-5 different users
- [ ] Check for error reports
- [ ] Schedule follow-up check in 24 hours

---

## Emergency Contacts

**Developer:** jbrunsfeld@uidaho.edu

**Backup locations:**
- MongoDB: `/backup/pre-migration-YYYYMMDD`
- Code: Git commit hash `_________`

---

**Time started:** _______________

**Time completed:** _______________

**Issues encountered:** _______________________________________________

**Resolution:** _____________________________________________________
