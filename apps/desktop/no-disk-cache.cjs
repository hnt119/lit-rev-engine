'use strict';
/** Next.js's supported cache-handler contract, only for the desktop wrapper.
 * The signed application is immutable. Research state belongs to FastAPI's
 * external data root; derived HTTP page/image entries are not persisted here.
 * Opaque cache keys and untrusted page data never become filesystem paths.
 */
module.exports=class DesktopNoDiskCache {
  async get(){return null;}
  async set(){}
  async revalidateTag(){}
  resetRequestCache(){}
};
