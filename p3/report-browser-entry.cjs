/* P3 browser build entrypoint. Build using esbuild; DO NOT put this
 * unbundled CommonJS entry directly in a <script> tag.
 * Installing this bundle by itself never unlocks or charges a user.
 * Only the existing SERVER-CONFIRMED report callback may invoke the API.
 */
"use strict";
const api=require("./report-integration.cjs");
if(typeof window!=="undefined"){
  Object.defineProperty(window,"JudunP3AuthorizedPriceNavigation",{
    value:api,writable:false,enumerable:false,configurable:false
  });
}
