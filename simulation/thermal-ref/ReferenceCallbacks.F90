! 仅提供冻结物性、出生项、边界数据和观测；矩阵装配及时间求解由 Elmer HeatSolver 完成。
MODULE ReferenceData
  USE DefUtils
  IMPLICIT NONE
  INTEGER :: nn, ne, nb, np, stride, step=0
  INTEGER, ALLOCATABLE :: mat(:), conn(:,:), owner(:), neighbour(:), axis(:), side(:), bn(:,:), pn(:,:), pe(:)
  INTEGER :: nk(3)
  REAL(KIND=dp) :: power, speed, first, last, preheat, birth, ambient, hc, radiation, af, ar, ff, fr, inactive_eps
  REAL(KIND=dp) :: rho(3), ts(3), tl(3), latent(3), knots(32,3), cp(32,3), kval(32,3)
  REAL(KIND=dp), ALLOCATABLE :: xleft(:), dx(:), volume(:), area(:), cooling(:), bare(:), bead(:), pw(:,:)
  REAL(KIND=dp), ALLOCATABLE :: oldt(:), fraction(:), prior(:), source(:), exposed(:), peak(:)
  REAL(KIND=dp), ALLOCATABLE :: birth_load(:,:)
  INTEGER, PARAMETER :: corner(3,8)=RESHAPE([0,0,0, 1,0,0, 1,1,0, 0,1,0, 0,0,1, 1,0,1, 1,1,1, 0,1,1],[3,8])
  LOGICAL, ALLOCATABLE :: dormant(:)
  REAL(KIND=dp) :: initial_energy=0, cumulative_source=0, cumulative_loss=0, cumulative_birth=0
  LOGICAL :: initialized=.FALSE.
CONTAINS
  SUBROUTINE ReadReference(Model)
    TYPE(Model_t) :: Model
    INTEGER :: i,j,u
    REAL(KIND=dp) :: stride_real
    IF (initialized) RETURN
    OPEN(NEWUNIT=u,FILE='reference.dat',STATUS='old',ACTION='read')
    READ(u,*) nn,ne,nb,np
    READ(u,*) power,speed,first,last,preheat,birth,ambient,hc,radiation,af,ar,ff,fr,inactive_eps,stride_real
    stride=INT(stride_real)
    DO i=1,3
      READ(u,*) rho(i),ts(i),tl(i),latent(i),nk(i)
      IF(nk(i)>32) CALL Fatal('Reference','Material table too large')
      DO j=1,nk(i)
        READ(u,*) knots(j,i),cp(j,i),kval(j,i)
      END DO
    END DO
    ALLOCATE(mat(ne),conn(8,ne),xleft(ne),dx(ne),volume(ne),fraction(ne),prior(ne))
    ALLOCATE(owner(nb),neighbour(nb),axis(nb),side(nb),area(nb),cooling(nb),bare(nb),bead(nb),bn(4,nb))
    ALLOCATE(pe(np),pn(8,np),pw(8,np),oldt(nn),source(nb),exposed(nb),peak(nn))
    ALLOCATE(dormant(nn))
    ALLOCATE(birth_load(8,ne))
    DO i=1,ne
      READ(u,*) mat(i),xleft(i),dx(i),volume(i),conn(:,i)
    END DO
    DO i=1,nb
      READ(u,*) owner(i),neighbour(i),axis(i),side(i),area(i),cooling(i),bare(i),bead(i),bn(:,i)
    END DO
    DO i=1,np
      READ(u,*) pe(i),pn(:,i),pw(:,i)
    END DO
    CLOSE(u)
    IF(Model%Mesh%NumberOfNodes/=nn) CALL Fatal('Reference','Unexpected mesh node count')
    DO i=1,ne
      IF(ANY(Model%Mesh%Elements(i)%NodeIndexes/=conn(:,i))) CALL Fatal('Reference','Bulk ordering changed')
    END DO
    DO i=1,nb
      IF(ANY(Model%Mesh%Elements(ne+i)%NodeIndexes/=bn(:,i))) CALL Fatal('Reference','Boundary ordering changed')
    END DO
    initialized=.TRUE.
  END SUBROUTINE

  FUNCTION Heat(t,m) RESULT(h)
    REAL(KIND=dp), INTENT(IN) :: t
    INTEGER, INTENT(IN) :: m
    REAL(KIND=dp) :: h,a,b,d,gradient
    INTEGER :: j
    h=0
    ! 求解中间迭代允许端点切线延拓；最终结果在观测器检查声明温度域。
    IF(t<knots(1,m)) THEN
      h=cp(1,m)*(t-knots(1,m))
      RETURN
    END IF
    DO j=1,nk(m)-1
      a=knots(j,m); b=MIN(t,knots(j+1,m))
      IF(b<=a) EXIT
      d=b-a; gradient=(cp(j+1,m)-cp(j,m))/(knots(j+1,m)-a)
      h=h+cp(j,m)*d+0.5_dp*gradient*d*d
    END DO
    IF(t>knots(nk(m),m)) h=h+cp(nk(m),m)*(t-knots(nk(m),m))
    h=h+latent(m)*MAX(0._dp,MIN(1._dp,(t-ts(m))/(tl(m)-ts(m))))
  END FUNCTION

  FUNCTION Capacity(t,m) RESULT(c)
    REAL(KIND=dp), INTENT(IN) :: t
    INTEGER, INTENT(IN) :: m
    REAL(KIND=dp) :: c,w
    INTEGER :: j
    j=1
    DO WHILE(j<nk(m)-1)
      IF(t<knots(j+1,m)) EXIT
      j=j+1
    END DO
    w=MAX(0._dp,MIN(1._dp,(t-knots(j,m))/(knots(j+1,m)-knots(j,m))))
    c=(1-w)*cp(j,m)+w*cp(j+1,m)
    IF(t>=ts(m).AND.t<tl(m)) c=c+latent(m)/(tl(m)-ts(m))
  END FUNCTION

  FUNCTION Conductivity(t,m) RESULT(k)
    REAL(KIND=dp), INTENT(IN) :: t
    INTEGER, INTENT(IN) :: m
    REAL(KIND=dp) :: k,w
    INTEGER :: j
    j=1
    DO WHILE(j<nk(m)-1)
      IF(t<knots(j+1,m)) EXIT
      j=j+1
    END DO
    w=MAX(0._dp,MIN(1._dp,(t-knots(j,m))/(knots(j+1,m)-knots(j,m))))
    k=(1-w)*kval(j,m)+w*kval(j+1,m)
  END FUNCTION

  FUNCTION Fill(e,t) RESULT(f)
    INTEGER, INTENT(IN) :: e
    REAL(KIND=dp), INTENT(IN) :: t
    REAL(KIND=dp) :: f
    f=1
    IF(mat(e)==3) f=MAX(0._dp,MIN(1._dp,(MIN(last,first+MAX(0._dp,t)*speed)-xleft(e))/dx(e)))
    IF(f<1.e-10_dp) f=0
    IF(f>1._dp-1.e-10_dp) f=1
  END FUNCTION

  FUNCTION Integral(a,b,center) RESULT(w)
    REAL(KIND=dp), INTENT(IN) :: a,b,center
    REAL(KIND=dp) :: w,lo,hi,r
    lo=a-center; hi=b-center; r=SQRT(3._dp)
    w=(fr*ar*(ERF(r*MIN(hi,0._dp)/ar)-ERF(r*MIN(lo,0._dp)/ar)) &
       +ff*af*(ERF(r*MAX(hi,0._dp)/af)-ERF(r*MAX(lo,0._dp)/af)))/(ff*af+fr*ar)
  END FUNCTION

  FUNCTION BoundaryIndex() RESULT(b)
    INTEGER :: b
    TYPE(Element_t), POINTER :: element
    element=>GetCurrentElement()
    b=element%ElementIndex-ne
    IF(b<1.OR.b>nb) CALL Fatal('Reference','Unexpected boundary index')
  END FUNCTION

  FUNCTION BulkIndex() RESULT(e)
    INTEGER :: e
    TYPE(Element_t), POINTER :: element
    element=>GetCurrentElement()
    e=element%ElementIndex
    IF(e<1.OR.e>ne) CALL Fatal('Reference','Unexpected bulk index')
  END FUNCTION

  FUNCTION Energy(t,f) RESULT(u)
    REAL(KIND=dp), INTENT(IN) :: t(:),f(:)
    REAL(KIND=dp) :: u
    INTEGER :: e,j
    u=0
    DO e=1,ne
      DO j=1,8
        u=u+rho(mat(e))*f(e)*volume(e)*Heat(t(conn(j,e)),mat(e))/8
      END DO
    END DO
  END FUNCTION
END MODULE

SUBROUTINE ReferencePrepare(Model,Solver,dt,TransientSimulation)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  TYPE(Solver_t), TARGET :: Solver
  REAL(KIND=dp) :: dt
  LOGICAL :: TransientSimulation
  TYPE(Variable_t), POINTER :: temp
  INTEGER :: i,e,j,n,u,k,d
  REAL(KIND=dp) :: now,center,lo,hi,whole,deposited,ownfill,otherfill,weight
  CALL ReadReference(Model)
  temp=>VariableGet(Model%Mesh%Variables,'Temperature')
  IF(.NOT.ASSOCIATED(temp)) CALL Fatal('Reference','Temperature variable absent')
  IF(step==0) THEN
    oldt=birth
    DO e=1,ne
      IF(mat(e)/=3) oldt(conn(:,e))=preheat
    END DO
    DO i=1,nn
      temp%Values(temp%Perm(i))=oldt(i)
      IF(ASSOCIATED(temp%PrevValues)) temp%PrevValues(temp%Perm(i),:)=oldt(i)
    END DO
    peak=oldt
    DO e=1,ne
      prior(e)=MAX(inactive_eps,Fill(e,0._dp))
    END DO
    initial_energy=Energy(oldt,prior)
    OPEN(NEWUNIT=u,FILE='history.csv',STATUS='replace')
    WRITE(u,'(A)') 'time_s,source_j,loss_j,birth_j,energy_change_j,residual_j,deposit_volume_mm3,min_c,max_c'
    CLOSE(u)
    OPEN(NEWUNIT=u,FILE='sensors.dat',STATUS='replace'); CLOSE(u)
  END IF
  DO i=1,nn
    oldt(i)=temp%Values(temp%Perm(i))
  END DO
  now=GetTime()
  DO e=1,ne
    prior(e)=MAX(inactive_eps,Fill(e,MAX(0._dp,now-dt)))
    fraction(e)=MAX(inactive_eps,Fill(e,now))
  END DO
  ! 空域自由节点固定为填丝温度；否则极小虚质量会放大相邻出生项，污染后续激活。
  dormant=.TRUE.
  DO e=1,ne
    IF(Fill(e,now)>0) dormant(conn(:,e))=.FALSE.
  END DO
  birth_load=0
  DO e=1,ne
    IF(fraction(e)<=prior(e)) CYCLE
    ! Hex8 一致载荷的归一化映射为三次张量积 [[2/3,1/3],[1/3,2/3]]。
    ! 逆映射使积分后的出生载荷与集中质量的节点冷焓一致，防止跨节点扣除热量。
    DO j=1,8
      DO k=1,8
        weight=1
        DO d=1,3
          IF(corner(d,j)==corner(d,k)) THEN
            weight=weight*2
          ELSE
            weight=-weight
          END IF
        END DO
        birth_load(j,e)=birth_load(j,e)+weight*(Heat(birth,mat(e))-Heat(oldt(conn(k,e)),mat(e)))
      END DO
    END DO
    birth_load(:,e)=birth_load(:,e)*rho(mat(e))*(fraction(e)-prior(e))/dt
  END DO
  center=first+speed*(now-dt/2)
  DO i=1,nb
    e=owner(i); n=neighbour(i)
    ownfill=Fill(e,now); otherfill=0
    IF(n>0) otherfill=Fill(n,now)
    IF(axis(i)==1) THEN
      exposed(i)=0
      IF(ownfill>0.AND.otherfill<=0) exposed(i)=1
    ELSE
      exposed(i)=MAX(0._dp,ownfill-otherfill)
    END IF
    exposed(i)=exposed(i)*cooling(i)
    source(i)=0
    IF(now-dt<(last-first)/speed-1.e-10_dp) THEN
      lo=MAX(xleft(e),first); hi=MAX(lo,MIN(xleft(e)+dx(e),MIN(center,last)))
      whole=Integral(xleft(e),xleft(e)+dx(e),center)
      deposited=Integral(lo,hi,center)
      source(i)=power*((whole-deposited)*bare(i)+deposited*bead(i))
    END IF
  END DO
  cumulative_source=cumulative_source+dt*SUM(source)
  DO i=1,nb
    DO j=1,4
      cumulative_loss=cumulative_loss+dt*area(i)*exposed(i) &
        *(hc*(oldt(bn(j,i))-ambient)+radiation*((oldt(bn(j,i))+273.15_dp)**4-(ambient+273.15_dp)**4))/4
    END DO
  END DO
  DO e=1,ne
    cumulative_birth=cumulative_birth+rho(mat(e))*volume(e)*(fraction(e)-prior(e))*Heat(birth,mat(e))
  END DO
  step=step+1
END SUBROUTINE

FUNCTION ReferenceDensity(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node,e
  REAL(KIND=dp) :: t,value
  e=BulkIndex()
  value=rho(mat(e))*fraction(e)
END FUNCTION

FUNCTION DormantCondition(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node
  REAL(KIND=dp) :: t,value
  value=-1
  IF(dormant(Node)) value=1
END FUNCTION

FUNCTION SecantCapacity(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node,m
  REAL(KIND=dp) :: t,value,delta
  m=mat(BulkIndex()); delta=t-oldt(Node)
  IF(ABS(delta)>1.e-7_dp) THEN
    value=(Heat(t,m)-Heat(oldt(Node),m))/delta
  ELSE
    value=Capacity((t+oldt(Node))/2,m)
  END IF
END FUNCTION

FUNCTION ReferenceConductivity(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node,e
  REAL(KIND=dp) :: t,value
  e=BulkIndex()
  value=Conductivity(oldt(Node),mat(e))*fraction(e)
END FUNCTION

FUNCTION BirthSource(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node,e,m,j
  REAL(KIND=dp) :: t,value
  e=BulkIndex(); m=mat(e)
  ! rho_new*delta_h 加上出生冷焓修正，避免新增质量凭空携带旧高温焓。
  value=0
  DO j=1,8
    IF(conn(j,e)==Node) value=birth_load(j,e)
  END DO
END FUNCTION

FUNCTION SurfaceFlux(Model,Node,t) RESULT(value)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: Node,b
  REAL(KIND=dp) :: t,value
  b=BoundaryIndex()
  value=source(b)/area(b)-exposed(b)*(hc*(oldt(Node)-ambient) &
        +radiation*((oldt(Node)+273.15_dp)**4-(ambient+273.15_dp)**4))
END FUNCTION

SUBROUTINE ReferenceObserve(Model,Solver,dt,TransientSimulation)
  USE ReferenceData
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  TYPE(Solver_t), TARGET :: Solver
  REAL(KIND=dp) :: dt
  LOGICAL :: TransientSimulation
  TYPE(Variable_t), POINTER :: temp
  REAL(KIND=dp), ALLOCATABLE :: current(:)
  REAL(KIND=dp) :: change,residual,deposit,tmin,tmax,value
  INTEGER :: i,j,e,u
  CHARACTER(LEN=80) :: filename
  temp=>VariableGet(Model%Mesh%Variables,'Temperature')
  ALLOCATE(current(nn))
  DO i=1,nn
    current(i)=temp%Values(temp%Perm(i))
  END DO
  peak=MAX(peak,current)
  change=Energy(current,fraction)-initial_energy
  residual=cumulative_source+cumulative_birth-cumulative_loss-change
  deposit=0; tmin=HUGE(1._dp); tmax=-HUGE(1._dp)
  DO e=1,ne
    IF(Fill(e,GetTime())>0) THEN
      tmin=MIN(tmin,MINVAL(current(conn(:,e))))
      tmax=MAX(tmax,MAXVAL(current(conn(:,e))))
    END IF
    IF(mat(e)==3) deposit=deposit+volume(e)*Fill(e,GetTime())
  END DO
  OPEN(NEWUNIT=u,FILE='history.csv',STATUS='old',POSITION='append')
  WRITE(u,'(*(ES23.15,:,","))') GetTime(),cumulative_source,cumulative_loss,cumulative_birth,change,residual,deposit,tmin,tmax
  CLOSE(u)
  OPEN(NEWUNIT=u,FILE='sensors.dat',STATUS='old',POSITION='append')
  WRITE(u,'(*(ES23.15,1X))') GetTime(),(SUM(current(pn(:,i))*pw(:,i)),i=1,np)
  CLOSE(u)
  IF(MOD(step,stride)==0.OR.step<=3) THEN
    WRITE(filename,'("field-",I5.5,".dat")') step
    OPEN(NEWUNIT=u,FILE=TRIM(filename),STATUS='replace')
    DO i=1,nn
      WRITE(u,'(2ES23.15)') current(i),peak(i)
    END DO
    CLOSE(u)
    WRITE(*,'(A,F8.3,A,F10.3,A,ES12.4)') 'REF time=',GetTime(),' max=',tmax,' energy residual=',residual
  END IF
  IF(tmin<19.9_dp.OR.tmax>3000.1_dp) CALL Fatal('Reference','Active temperature outside declared property domain')
  DEALLOCATE(current)
END SUBROUTINE
