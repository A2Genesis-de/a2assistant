import type { BillingTranslations } from './types_billing'

// Out-of-credits overlay copy (Nous vs. third-party providers), spread into en.ts.
export const enBilling: BillingTranslations = {
  billingBlock: {
    titleProvider: provider => `Out of credits — ${provider}`,
    fallbackMessage: 'Your account is out of credits. Add credits to keep going.',
    addCredits: 'Add credits',
    dismiss: 'Dismiss'
  }
}
