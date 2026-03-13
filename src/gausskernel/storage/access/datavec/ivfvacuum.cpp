/*
 * This file contains code from different sources, governed by different open source licenses.
 *
 * 1. Code originating from the PostgreSQL project:
 *    - Portions Copyright (c) 1996-2023, PostgreSQL Global Development Group
 *    - This code is licensed under the PostgreSQL License.
 *    - Permission is granted to use, copy, modify, and distribute this software in source and binary forms,
 *      provided that the above copyright notice, this condition list, and the following disclaimer
 *      are retained in source distributions, and reproduced in documentation/material provided with
 *      binary distributions.
 *
 * 2. Modifications and new code by Huawei Technologies Co., Ltd.:
 *    - Portions Copyright (c) 2024 Huawei Technologies Co.,Ltd.
 *    - This code is licensed under the Mulan Permissive Software License, Version 2 (Mulan PSL v2).
 *    - Full license text available at: http://license.coscl.org.cn/MulanPSL2
 *
 * 3. General Disclaimer (as required by the PostgreSQL License):
 *    - THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS
 *      OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 *      AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 *      CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 *      DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 *      DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 *      IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 *      OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * By using this file, you acknowledge that you must comply with all applicable terms of both the
 * PostgreSQL License and the Mulan PSL v2 for the respective code portions you utilize.
 * -------------------------------------------------------------------------
 *
 * ivfvacuum.cpp
 *
 * IDENTIFICATION
 *        src/gausskernel/storage/access/datavec/ivfvacuum.cpp
 *
 * -------------------------------------------------------------------------
 */
#include "postgres.h"

#include "access/generic_xlog.h"
#include "commands/vacuum.h"
#include "access/datavec/ivfflat.h"
#include "storage/buf/bufmgr.h"

/*
 * Bulk delete tuples from the index
 */
IndexBulkDeleteResult *ivfflatbulkdelete_internal(IndexVacuumInfo *info, IndexBulkDeleteResult *stats,
                                                  IndexBulkDeleteCallback callback, void *callbackState)
{
    uint16 pqTableNblk;
    uint32 pqDisTableNblk;
    uint16 matrixNblk;
    uint16 otherNblk;

    Relation index = info->index;
    IvfGetPQInfoFromMetaPage(index, &pqTableNblk, NULL, &pqDisTableNblk, NULL);
    IvfflatGetRbqInfoFromMetaPage(index, NULL, NULL, NULL, NULL, &matrixNblk,
                            NULL, &otherNblk, NULL, NULL, NULL);
    BlockNumber blkno = IVFFLAT_CHUNK_START_BLKNO + pqTableNblk + pqDisTableNblk + matrixNblk + otherNblk;
    BufferAccessStrategy bas = GetAccessStrategy(BAS_BULKREAD);

    if (stats == NULL)
        stats = (IndexBulkDeleteResult *)palloc0(sizeof(IndexBulkDeleteResult));

    /* Iterate over list pages */
    while (BlockNumberIsValid(blkno)) {
        Buffer cbuf;
        Page cpage;
        OffsetNumber coffno;
        OffsetNumber cmaxoffno;
        BlockNumber startPages[MaxOffsetNumber];
        ListInfo listInfo;

        cbuf = ReadBuffer(index, blkno);
        LockBuffer(cbuf, BUFFER_LOCK_SHARE);
        cpage = BufferGetPage(cbuf);

        cmaxoffno = PageGetMaxOffsetNumber(cpage);

        /* Iterate over lists */
        for (coffno = FirstOffsetNumber; coffno <= cmaxoffno; coffno = OffsetNumberNext(coffno)) {
            IvfflatList list = (IvfflatList)PageGetItem(cpage, PageGetItemId(cpage, coffno));

            startPages[coffno - FirstOffsetNumber] = list->startPage;
        }

        listInfo.blkno = blkno;
        blkno = IvfflatPageGetOpaque(cpage)->nextblkno;

        UnlockReleaseBuffer(cbuf);

        for (coffno = FirstOffsetNumber; coffno <= cmaxoffno; coffno = OffsetNumberNext(coffno)) {
            BlockNumber searchPage = startPages[coffno - FirstOffsetNumber];
            BlockNumber insertPage = InvalidBlockNumber;

            /* Iterate over entry pages */
            while (BlockNumberIsValid(searchPage)) {
                Buffer buf;
                Page page;
                GenericXLogState *state;
                OffsetNumber offno;
                OffsetNumber maxoffno;
                OffsetNumber deletable[MaxOffsetNumber];
                int ndeletable;

                vacuum_delay_point();

                buf = ReadBufferExtended(index, MAIN_FORKNUM, searchPage, RBM_NORMAL, bas);

                /*
                 * ambulkdelete cannot delete entries from pages that are
                 * pinned by other backends
                 *
                 * https://www.postgresql.org/docs/current/index-locking.html
                 */
                LockBufferForCleanup(buf);

                state = GenericXLogStart(index);
                page = GenericXLogRegisterBuffer(state, buf, 0);

                maxoffno = PageGetMaxOffsetNumber(page);
                ndeletable = 0;

                /* Find deleted tuples */
                for (offno = FirstOffsetNumber; offno <= maxoffno; offno = OffsetNumberNext(offno)) {
                    IndexTuple itup = (IndexTuple)PageGetItem(page, PageGetItemId(page, offno));
                    ItemPointer htup = &(itup->t_tid);

                    if (callback(htup, callbackState, InvalidOid, InvalidBktId)) {
                        deletable[ndeletable++] = offno;
                        stats->tuples_removed++;
                    } else
                        stats->num_index_tuples++;
                }

                /* Set to first free page */
                /* Must be set before searchPage is updated */
                if (!BlockNumberIsValid(insertPage) && ndeletable > 0)
                    insertPage = searchPage;

                searchPage = IvfflatPageGetOpaque(page)->nextblkno;

                if (ndeletable > 0) {
                    /* Delete tuples */
                    PageIndexMultiDelete(page, deletable, ndeletable);
                    GenericXLogFinish(state);
                } else
                    GenericXLogAbort(state);

                UnlockReleaseBuffer(buf);
            }

            /*
             * Update after all tuples deleted.
             *
             * We don't add or delete items from lists pages, so offset won't
             * change.
             */
            if (BlockNumberIsValid(insertPage)) {
                listInfo.offno = coffno;
                IvfflatUpdateList(index, listInfo, insertPage, InvalidBlockNumber, InvalidBlockNumber, MAIN_FORKNUM);
            }
        }
    }

    FreeAccessStrategy(bas);

    return stats;
}

/*
 * Clean up after a VACUUM operation
 */
IndexBulkDeleteResult *ivfflatvacuumcleanup_internal(IndexVacuumInfo *info, IndexBulkDeleteResult *stats)
{
    Relation rel = info->index;

    if (info->analyze_only)
        return stats;

    /* stats is NULL if ambulkdelete not called */
    /* OK to return NULL if index not changed */
    if (stats == NULL)
        return NULL;

    stats->num_pages = RelationGetNumberOfBlocks(rel);

    return stats;
}
