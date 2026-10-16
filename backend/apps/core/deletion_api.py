"""DELETE /api/objects/{kind}/{id}: one call for every kind of thing that an admin can delete."""

from django.http import Http404
from ninja import Router, Schema
from ninja.errors import HttpError

from .deletion import KINDS, DeleteError, delete

router = Router(tags=["deletion"])


class DeletedOut(Schema):
    name: str


class InUseOut(Schema):
    detail: str
    uses: list[str]


@router.delete("/objects/{kind}/{object_id}", response={200: DeletedOut, 409: InUseOut})
def delete_object(request, kind: str, object_id: int):
    if kind not in KINDS:
        raise Http404
    try:
        name = delete(kind, object_id, request.user)
    except DeleteError as error:
        if error.code == "not_found":
            raise Http404 from error
        if error.code == "forbidden":
            raise HttpError(403, "forbidden") from error
        if error.code in ("in_use", "entry_has_results"):
            return 409, InUseOut(detail=error.code, uses=error.uses)
        raise HttpError(422, error.code) from error
    return 200, DeletedOut(name=name)
