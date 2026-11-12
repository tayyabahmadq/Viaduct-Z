package com.viaduct.pay.ui

import java.util.Locale

/** 45000 -> "450.00" */
fun money(cents: Int): String = String.format(Locale.US, "%,.2f", cents / 100.0)
