# 🔐 Clerk DNS Setup - TO DO LATER

## ⚠️ IMPORTANT: Clerk is Currently in Development Mode

**What this means:**
- ✅ Backend deployment will work fine
- ✅ Admin panel will work fine
- ✅ API endpoints will work fine
- ❌ **User sign-in/sign-up on production site will NOT work until you complete this setup**

**When to do this:** After backend is deployed and tested successfully.

---

## 📋 What You Need to Do

Add **5 CNAME records** to your domain DNS settings in Vercel to enable Clerk production mode.

---

## 🚀 Quick Setup Steps (15 minutes)

### Step 1: Go to Vercel DNS Settings

1. Go to: https://vercel.com/dashboard
2. Select your project: **ajunisexsalon.com**
3. Click **Settings** tab
4. Click **Domains** in left sidebar
5. Find **ajunisexsalon.com**
6. Click **Edit** or **Manage DNS**

### Step 2: Add 5 CNAME Records

Click **Add Record** for each one below:

#### Record 1: Clerk Accounts
```
Type: CNAME
Name: accounts
Value: accounts.clerk.services
TTL: Auto (or 3600)
```

#### Record 2: Clerk API
```
Type: CNAME
Name: clerk
Value: clerk.clerk.services  
TTL: Auto (or 3600)
```

#### Record 3: Clerk Frontend API
```
Type: CNAME
Name: clerk.ajunisexsalon
Value: frontend-api.clerk.services
TTL: Auto (or 3600)
```

#### Record 4: Clerk Clerk API
```
Type: CNAME  
Name: clerk.ajunisexsalon.clerk
Value: clerk-api.clerk.services
TTL: Auto (or 3600)
```

#### Record 5: Clerk Accounts URL
```
Type: CNAME
Name: clerk.ajunisexsalon.accounts
Value: accounts.clerk.services
TTL: Auto (or 3600)
```

### Step 3: Save and Wait

1. Click **Save** for each record
2. Wait **5-30 minutes** for DNS propagation
3. You can check status at: https://dnschecker.org

### Step 4: Verify in Clerk Dashboard

1. Go to: https://dashboard.clerk.com
2. Select your **AJ Salon** project
3. Go to **Settings** → **Domains**
4. You should see all 5 domains verified with ✅ green checkmarks

### Step 5: Switch to Production Mode

1. In Clerk Dashboard, go to **Settings** → **Danger Zone**
2. Click **Switch to Production Mode**
3. Confirm the switch
4. Done! 🎉

---

## ✅ How to Test After Setup

1. Visit your production site: https://ajunisexsalon.com
2. Click **Sign In** or **Sign Up** button
3. Should see Clerk authentication modal
4. Try creating a test account
5. Should work without errors

---

## 🆘 Troubleshooting

### DNS Records Not Showing Up?
- Wait 30 minutes for full propagation
- Clear your browser cache
- Try in incognito/private window

### Clerk Still Says "Development Mode"?
- Verify all 5 CNAME records are added correctly
- Check DNS propagation: https://dnschecker.org
- Contact Clerk support if records are correct but not verified

### Sign In Shows Error?
- Check browser console for errors
- Verify `CLERK_SECRET_KEY` in Render environment variables
- Verify `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` in frontend

---

## 📚 Detailed Guides Available

For more detailed step-by-step instructions, see:
- `START-HERE-CLERK-DNS.md` - Complete overview
- `VERCEL-DNS-STEP-BY-STEP.md` - Detailed Vercel DNS guide
- `CLERK-DNS-QUICK-SETUP.md` - Quick reference
- `CLERK-PRODUCTION-LOCAL-TESTING.md` - Testing guide

---

## 🎯 Summary

**Why this is needed:**
- Clerk development mode only works on localhost
- Production authentication requires custom domain setup
- These 5 DNS records tell Clerk your domain is verified

**Impact:**
- Without this: Users cannot sign in/sign up on production site
- With this: Full authentication functionality on ajunisexsalon.com

**Priority:** 
- Not urgent for backend deployment
- **Must do before frontend goes fully live**

---

## ✅ Checklist

When you're ready to implement:

- [ ] Backend deployed to Render successfully
- [ ] Backend tested and working
- [ ] Ready to enable authentication on production
- [ ] Add 5 CNAME records in Vercel DNS
- [ ] Wait for DNS propagation (5-30 min)
- [ ] Verify records in Clerk Dashboard
- [ ] Switch Clerk to Production Mode
- [ ] Test sign-in/sign-up on production site
- [ ] Done! ✨

---

**Estimated Time:** 15 minutes setup + 30 minutes wait time = 45 minutes total

**When to do:** After backend is deployed and tested, before launching site to users.

---

*Created: August 23, 2026*  
*Developer: Sonik Lamsal*  
*Project: AJ Salon - ajunisexsalon.com*
